from fastapi import FastAPI, HTTPException, Body, Query, UploadFile, File
import hashlib
import os
import shutil
import aiofiles
import base64
import threading
import json
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel

# from ..insights.graph_insights import (
#     get_suspects, get_alerts, get_timeline, get_summary, compute_insights
# )
# from ..insights import graph_insights
# from ..insights.insight_schema import (
#     GraphPayload, SuspectDetail, TransactionAlert, TimelineEvent, GraphSummary,
#     EntityDetail, RelationDetail,
#     GraphRenderPayload, RenderNode, RenderLink,
# )
# from ..db.postgres_client import PostgresClient
# from ..db.redis_client import RedisClient

from insights.graph_insights import (
    get_suspects, get_alerts, get_timeline, get_summary, compute_insights
)
from insights import graph_insights
from insights.insight_schema import (
    GraphPayload, SuspectDetail, TransactionAlert, TimelineEvent, GraphSummary,
    EntityDetail, RelationDetail,
    GraphRenderPayload, RenderNode, RenderLink,
)
from db.postgres_client import PostgresClient
from db.redis_client import RedisClient

# Import all pipeline runners from modular analysis packages
from analysis.graph_summary.summarize import run_summary
from analysis.timeline_reconstruction.reconstruct import run_reconstruction
from analysis.rule_validation.validate import run_validation_pipeline
from analysis.rule_validation.relation_analyzer import get_relation_summary_and_metadata
from Gemini_Engine.main import run_engine

from api.case_pipeline import stage_case_inputs, validate_case_id
from api.case_report import build_case_report_markdown, refresh_case_report_from_outputs

from db.artifact_registry import (
    check_redis_artifacts,
    sync_redis_artifacts,
)


# ---------------------------------------------------------------------------
# Helper: legacy raw-graph payload (kept for backward compatibility)
# ---------------------------------------------------------------------------

def get_graph_payload() -> GraphPayload:
    if not graph_insights._GRAPH_DATA:
        compute_insights()
    return GraphPayload(
        master_entities=[EntityDetail(**m) for m in graph_insights._GRAPH_DATA.get("master_entities", [])],
        relations=[RelationDetail(**r) for r in graph_insights._GRAPH_DATA.get("relations", [])]
    )

# ---------------------------------------------------------------------------
# Helper: build a human-readable label for a master entity.
# This is the canonical name-resolution logic — frontend must NOT duplicate it.
# ---------------------------------------------------------------------------

def _entity_label(master: dict) -> str:
    """Return the best human-readable display name for a master entity."""
    resolved = master.get("resolved_values", [])
    master_type = master.get("master_type", "")

    # For PERSON entities, prefer a token that looks like a proper name
    if master_type == "PERSON":
        for val in resolved:
            v = val.strip()
            # Skip phone numbers, account IDs, device IDs, social handles, emails
            if (not v.startswith("98") and not v.startswith("91")
                    and not v.startswith("acc") and not v.startswith("@")
                    and "@" not in v and not v.startswith("android")
                    and not v.startswith("watch") and not v.startswith("tracker")
                    and not any(c.isdigit() for c in v)
                    and len(v) > 2):
                return v.title()

    # For PLACE, INFRASTRUCTURE, ENTITY — first resolved value is usually descriptive
    if resolved:
        label = resolved[0].strip()
        # Clean up synthetic IDs like "email_address_cc44d0c6"
        if "_" in label and len(label) > 20:
            return label.replace("_", " ").title()
        return label.replace("_", " ").title() if "_" in label else label.title()

    return master.get("master_id", "Unknown")

# ---------------------------------------------------------------------------
# Helper: build the visualization-ready graph render payload
# ---------------------------------------------------------------------------

def get_graph_render_payload() -> GraphRenderPayload:
    """
    Adapter that converts unified_graph.json into clean visualization data.
    Enriches nodes with risk scores from suspect analysis.
    The frontend receives ONLY this — no raw entity resolution data.
    """
    if not graph_insights._GRAPH_DATA:
        compute_insights()
    if not graph_insights._SUSPECTS:
        compute_insights()

    # Sync risk scores with premium Person Risk Profiles from Risk Intelligence Engine
    import json
    profiles_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analysis", "rule_validation", "output", "person_risk_profiles.json")
    risk_lookup = {}
    if os.path.exists(profiles_path):
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                profs = json.load(f)
                risk_lookup = {p["person_id"]: p["risk_score"] for p in profs}
        except Exception:
            pass

    if not risk_lookup:
        risk_lookup = {
            s.master_id: s.risk_score
            for s in graph_insights._SUSPECTS
        }

    masters = graph_insights._GRAPH_DATA.get("master_entities", [])
    relations = graph_insights._GRAPH_DATA.get("relations", [])

    nodes: list[RenderNode] = []
    for m in masters:
        mid = m["master_id"]
        entity_types = m.get("entity_types", [])
        is_person = m.get("master_type", "ENTITY") == "PERSON"
        nodes.append(RenderNode(
            id=mid,
            label=_entity_label(m),
            type=m.get("master_type", "ENTITY"),
            sub_type=entity_types[0] if entity_types else "UNKNOWN",
            risk_score=risk_lookup.get(mid, 0.0) if is_person else 0.0,
        ))

    links: list[RenderLink] = []
    for r in relations:
        links.append(RenderLink(
            source=r["source"],
            target=r["target"],
            type=r.get("relation", "RELATED"),
            confidence=float(r.get("confidence", 1.0)),
        ))

    return GraphRenderPayload(nodes=nodes, links=links)


# ── Upload directory (local filesystem storage) ──────────────
BACKEND_DIR = Path(os.path.dirname(os.path.dirname(__file__)))
DATA_ROOT = Path(os.getenv("TATHYA_DATA_DIR", str(BACKEND_DIR)))
DATA_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = str(DATA_ROOT / "uploads")
CASE_DATA_DIR = DATA_ROOT / "case_data"
os.makedirs(UPLOAD_DIR, exist_ok=True)
CASE_PROCESS_LOCK = threading.Lock()

# Allowed file extensions
ALLOWED_EXTENSIONS = {"csv", "json", "txt", "pdf", "wav", "jpg", "jpeg", "png", "log"}
TEXT_EXTENSIONS = {"csv", "json", "txt", "log"}


def read_raw_evidence_content(path: str, ext: str) -> tuple[str, str]:
    """Return upload content as UTF-8 text or base64 text for Supabase storage."""
    with open(path, "rb") as f:
        raw = f.read()
    if ext in TEXT_EXTENSIONS:
        return raw.decode("utf-8", errors="replace"), "utf-8"
    return base64.b64encode(raw).decode("ascii"), "base64"

app = FastAPI(title="TATHYA-DF Insights & Forensic API", version="1.1.0")

# Enable CORS for the frontend Vite server
configured_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
local_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(local_origins + configured_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database and Cache clients
db = PostgresClient()
cache = RedisClient()

@app.on_event("startup")
def startup_event():
    """Ensure database tables exist on API startup."""
    if db.engine:
        try:
            db.create_tables()
            print("[API Startup] Supabase PostgreSQL tables verified/created.")
        except Exception as e:
            print(f"[API Startup] Failed to initialize PostgreSQL tables: {e}")
    else:
        print("[API Startup] WARNING: PostgreSQL client not connected.")

# ── REQUEST SCHEMAS ──────────────────────────────────────────

class CaseCreate(BaseModel):
    case_id: str
    title: str
    description: Optional[str] = ""
    investigator: Optional[str] = ""
    metadata: Optional[dict] = None

class NoteCreate(BaseModel):
    content: str
    author: Optional[str] = "analyst"
    entity_ref: Optional[str] = None
    tags: Optional[List[str]] = None

class EvidenceCreate(BaseModel):
    filename: str
    file_type: Optional[str] = "csv"
    file_hash: Optional[str] = ""
    record_count: Optional[int] = 0
    metadata: Optional[dict] = None

class EntityAssessmentCreate(BaseModel):
    case_id: str
    entity_id: str
    status: str  # ACTIVE | CLEARED | PERSON_OF_INTEREST | PRIORITY_TARGET
    reason: Optional[str] = None

# ── ORIGINAL GRAPH & INSIGHTS ENDPOINTS ──────────────────────

@app.get("/api/graph", response_model=GraphPayload)
def read_graph(dataset: str = "UnifiedGraph"):
    """Returns the full unified graph. Caches in Redis and queries Neo4j."""
    # Log query to Postgres
    db.log_query(
        query_text=f"Fetched full graph for dataset '{dataset}'",
        query_type="graph_fetch",
        result_count=1,
        case_id=None
    )
    return get_graph_payload()

@app.get("/graph/render", response_model=GraphRenderPayload)
def read_graph_render():
    """
    Returns visualization-ready graph data for react-force-graph-3d.
    All graph interpretation (name resolution, risk scoring, type mapping)
    is performed here. The frontend receives only clean nodes + links.
    """
    return get_graph_render_payload()

@app.get("/api/insights/suspects", response_model=List[SuspectDetail])
def read_suspects():
    """Returns a list of suspects scored by risk, synced with the core Risk Intelligence Engine."""
    import os
    import json
    profiles_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analysis", "rule_validation", "output", "person_risk_profiles.json")
    if os.path.exists(profiles_path):
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                profs = json.load(f)
                
            suspect_details = []
            for p in profs:
                # Build list of reasons from triggered rules or evidence
                reasons = []
                for ev in p.get("evidence", []):
                    rule_name = ev.get("rule_name", "")
                    contrib = ev.get("weighted_contribution", 0.0)
                    reasons.append(f"{rule_name} (Contribution: +{contrib:.1f}%)")
                if not reasons:
                    reasons = ["No suspicious forensic rules triggered. Risk based on graph connectivity."]
                    
                g_metrics = p.get("graph_metrics", {})
                
                suspect_details.append(SuspectDetail(
                    master_id=p["person_id"],
                    name=p["name"],
                    risk_score=p["risk_score"],
                    degree_centrality=g_metrics.get("degree", 0.0),
                    betweenness_centrality=g_metrics.get("betweenness", 0.0),
                    identifiers=p.get("identifiers", []),
                    entity_types=p.get("entity_types", []),
                    reasons=reasons
                ))
            # Sort suspects by risk score descending
            suspect_details.sort(key=lambda s: s.risk_score, reverse=True)
            return suspect_details
        except Exception as e:
            print(f"Error loading person risk profiles for suspects endpoint: {e}")
            pass
            
    return get_suspects()

@app.get("/api/insights/transactions", response_model=List[TransactionAlert])
def read_transactions():
    """Returns flagged transactions (smurfing, circular flows, etc.)."""
    return get_alerts()

@app.get("/api/timeline")
def read_timeline():
    """Returns the generated timeline.json produced by the timeline reconstruction layer."""
    import os
    import json
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analysis", "timeline_reconstruction", "timeline.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"scenes": []}

@app.get("/api/insights/summary", response_model=GraphSummary)
def read_summary():
    """Returns global metrics of the graph."""
    return get_summary()

@app.get("/api/insights/risk-profiles")
def read_person_risk_profiles():
    """Returns the generated person risk profiles."""
    import os
    import json
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analysis", "rule_validation", "output", "person_risk_profiles.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

@app.get("/api/insights/relationship-profiles")
def read_relationship_risk_profiles():
    """Returns the generated relationship risk profiles."""
    import os
    import json
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analysis", "rule_validation", "output", "relationship_risk_profiles.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

@app.get("/api/insights/relation-details")
def read_relation_details(source: str, target: str):
    """
    Computes/returns detailed metadata, interaction counts, raw link list,
    and a human-readable summary connecting source and target nodes.
    """
    try:
        return get_relation_summary_and_metadata(source, target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── NEW POSTGRES CASES & USER INPUTS ENDPOINTS ───────────────

@app.get("/api/cases")
def list_cases(status: Optional[str] = None):
    """List all investigation cases stored in Supabase."""
    try:
        return db.list_cases(status=status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cases")
def create_case(case: CaseCreate):
    """Create a new case in Supabase PostgreSQL."""
    try:
        validate_case_id(case.case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return db.create_case(
            case_id=case.case_id,
            title=case.title,
            description=case.description,
            investigator=case.investigator,
            metadata=case.metadata
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    """Get details of a specific case, including metadata, notes, and evidence."""
    data = db.get_case(case_id=case_id)
    if not data:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Enrich with notes and evidence list
    data["notes"] = db.get_notes(case_id=case_id)
    data["evidence_files"] = db.get_evidence(case_id=case_id)
    return data

@app.get("/api/cases/{case_id}/export-pdf")
def export_case_pdf(case_id: str):
    """
    Generates and returns the Gemini-created investigation report as a beautifully styled PDF.
    """
    import os
    from fastapi.responses import FileResponse
    from api.pdf_generator import markdown_to_pdf
    
    try:
        validate_case_id(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Rebuild this case's report from its own persisted manifest, graph and
    # timeline. This refreshes report formatting/content without requiring the
    # investigator to upload or process the evidence a second time.
    case_data = db.get_case(case_id=case_id)
    if not case_data:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    case_output_dir = CASE_DATA_DIR / case_id / "outputs"
    try:
        report_markdown = refresh_case_report_from_outputs(
            case_id=case_id,
            case_title=case_data.get("title") or case_id,
            output_dir=case_output_dir,
        )
        pdf_output_path = case_output_dir / f"investigation_report_{case_id}.pdf"
        markdown_to_pdf(report_markdown, pdf_output_path, case_id)
        
        return FileResponse(
            path=str(pdf_output_path),
            filename=f"TATHYA-DF_Investigation_Report_{case_id}.pdf",
            media_type="application/pdf"
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")

@app.post("/api/cases/{case_id}/notes")
def add_note(case_id: str, note: NoteCreate):
    """Add an investigator note or annotation to a case."""
    try:
        return db.add_note(
            case_id=case_id,
            content=note.content,
            author=note.author,
            entity_ref=note.entity_ref,
            tags=note.tags
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/cases/{case_id}/notes")
def get_notes(case_id: str):
    """Get all notes for a case."""
    return db.get_notes(case_id=case_id)

@app.post("/api/cases/{case_id}/evidence")
def add_evidence(case_id: str, ev: EvidenceCreate):
    """Log an evidence file uploaded for a case."""
    try:
        return db.add_evidence(
            case_id=case_id,
            filename=ev.filename,
            file_type=ev.file_type,
            file_hash=ev.file_hash,
            record_count=ev.record_count,
            metadata=ev.metadata
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/cases/{case_id}/evidence")
def get_evidence(case_id: str):
    """Get all logged evidence files for a case."""
    return db.get_evidence(case_id=case_id)

@app.post("/api/cases/{case_id}/upload")
async def upload_evidence_file(case_id: str, file: UploadFile = File(...)):
    """
    Upload a physical evidence file for a case.
    - Streams file to backend/uploads/{case_id}/
    - Computes SHA-256 hash
    - Records metadata in PostgreSQL evidence_files table
    """
    try:
        validate_case_id(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Validate file extension
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{ext}' not allowed. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Ensure case exists
    case_data = db.get_case(case_id=case_id)
    if not case_data:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    # Create upload directory for this case
    case_upload_dir = os.path.join(UPLOAD_DIR, case_id)
    os.makedirs(case_upload_dir, exist_ok=True)

    # Sanitize filename to prevent directory traversal
    safe_filename = os.path.basename(file.filename or "upload")
    dest_path = os.path.join(case_upload_dir, safe_filename)

    # Stream file to disk and compute SHA-256 hash simultaneously
    hasher = hashlib.sha256()
    try:
        with open(dest_path, "wb") as dest:
            while chunk := await file.read(1024 * 64):  # 64KB chunks
                hasher.update(chunk)
                dest.write(chunk)
    except Exception as e:
        # Clean up partial file on error
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=500, detail=f"File write error: {e}")

    file_hash = hasher.hexdigest()
    file_size = os.path.getsize(dest_path)

    # Record metadata in PostgreSQL
    try:
        record = db.add_evidence(
            case_id=case_id,
            filename=safe_filename,
            file_type=ext,
            file_hash=file_hash,
            record_count=0,
            metadata={
                "original_filename": file.filename,
                "content_type": file.content_type,
                "size_bytes": file_size,
                "local_path": dest_path,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    # Store the raw user input in Supabase too.
    try:
        raw_content, content_encoding = read_raw_evidence_content(dest_path, ext)
        raw_record = db.add_raw_evidence_content(
            evidence_id=record.get("id"),
            case_id=case_id,
            filename=safe_filename,
            file_type=ext,
            content_text=raw_content,
            content_encoding=content_encoding,
            file_hash=file_hash,
            size_bytes=file_size,
            metadata={
                "original_filename": file.filename,
                "content_type": file.content_type,
                "local_path": dest_path,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Raw evidence storage error: {e}")

    return {
        "id": record.get("id"),
        "filename": safe_filename,
        "file_type": ext,
        "file_hash": file_hash,
        "size_bytes": file_size,
        "raw_storage": raw_record,
        "status": "uploaded",
    }

# ── ENTITY ASSESSMENT ENDPOINTS ──────────────────────────────

VALID_STATUSES = {"ACTIVE", "CLEARED", "PERSON_OF_INTEREST", "PRIORITY_TARGET"}

@app.post("/api/entity-assessments")
def upsert_entity_assessment(assessment: EntityAssessmentCreate):
    """
    Create or update an investigator's assessment of a graph entity.
    Upserts by (case_id, entity_id). Does NOT modify Neo4j or master_entities.
    """
    if assessment.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{assessment.status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )
    try:
        result = db.upsert_entity_assessment(
            case_id=assessment.case_id,
            entity_id=assessment.entity_id,
            status=assessment.status,
            reason=assessment.reason,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/entity-assessments/{case_id}")
def get_entity_assessments(case_id: str):
    """
    Return all investigator assessments for a case, keyed by entity_id.
    Example: { "P001": { "status": "CLEARED", "reason": "Verified alibi" } }
    """
    try:
        return db.get_entity_assessments(case_id=case_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── AUDIT & SYSTEM STATUS ENDPOINTS ─────────────────────────

@app.get("/api/audit")
def get_audit(limit: int = Query(default=50, ge=1, le=200)):
    """Retrieve audit trail logs of investigator actions."""
    return db.get_audit_log(limit=limit)

@app.get("/api/cache/stats")
def get_cache_stats():
    """Retrieve statistics of Upstash Redis cache (hits/keys)."""
    return cache.get_stats() if cache.connected else {"connected": False}

@app.post("/api/cache/clear")
def clear_insights_cache():
    """Manually invalidate cached graph insights."""
    import insights.graph_insights as gi
    gi._GRAPH_DATA = {}
    gi._SUSPECTS = []
    gi._ALERTS = []
    gi._TIMELINE = []
    gi._SUMMARY = None
    if cache.connected:
        count = cache.invalidate_insights()
        return {"status": "success", "invalidated_keys_count": count}
    return {"status": "success", "message": "In-memory cache cleared successfully."}

@app.get("/api/artifacts/status")
def get_artifacts_status():
    """Check whether processed inputs and layer caches are stored in Upstash Redis."""
    if not cache.connected:
        return {"ok": False, "backend": "upstash_redis", "connected": False}
    try:
        return check_redis_artifacts(cache)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/artifacts/sync")
def sync_artifacts_to_redis():
    """Store/update processed inputs and layer caches in Upstash Redis."""
    if not cache.connected:
        raise HTTPException(status_code=503, detail="Redis not connected")
    try:
        return sync_redis_artifacts(cache)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/case/process")
def process_case(case_id: str = Body(..., embed=True)):
    """Process uploaded evidence in a per-case workspace.

    The previous implementation copied one case into shared integration folders,
    deleted the shared input files, and overwrote global graph/timeline outputs.
    This implementation uses explicit case-scoped input and output paths and
    serialises execution because some legacy preprocessors still use process-wide
    working state.
    """
    try:
        validate_case_id(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    case_data = db.get_case(case_id=case_id)
    if not case_data:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    case_upload_dir = Path(UPLOAD_DIR) / case_id
    case_workspace = CASE_DATA_DIR / case_id
    output_dir = case_workspace / "outputs"
    graph_path = output_dir / "unified_graph.json"
    summary_path = output_dir / "summary.json"
    timeline_path = output_dir / "timeline.json"
    validation_dir = output_dir / "validation"

    # A lock prevents two requests from entering legacy preprocessor code at once.
    with CASE_PROCESS_LOCK:
        try:
            staged = stage_case_inputs(case_upload_dir, case_workspace, evidence_records=db.get_evidence(case_id=case_id))
            import shutil
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_dir / "manifest.json", "w", encoding="utf-8") as handle:
                json.dump({"case_id": case_id, "status": "processing"}, handle)

            db.log_query(
                query_text=f"Triggered case-scoped processing pipeline for case '{case_id}'",
                query_type="pipeline_trigger",
                result_count=len(staged["staged_sources"]),
                case_id=case_id,
            )

            print(f"[API] Starting case-scoped pipeline for {case_id}")
            from Graph_Integration_Layer.main import main as run_integration_pipeline
            pipeline_result = run_integration_pipeline(
                data_dir=staged["input_dir"],
                vehicle_data_dir=staged["vehicle_input_dir"],
                output_path=graph_path,
                source_manifest=staged["source_manifest"],
            ) or {}
            source_processing = pipeline_result.get("preprocessor_status", [])

            if not graph_path.exists():
                raise RuntimeError("Graph integration completed without creating a unified graph file.")

            with open(graph_path, "r", encoding="utf-8") as handle:
                graph_data = json.load(handle)

            if not isinstance(graph_data, dict):
                raise RuntimeError("The graph output is not a valid JSON object.")

            print(f"[API] Building graph summary for {case_id}")
            summary = run_summary(
                graph_path=graph_path,
                output_path=summary_path,
                prefer_neo4j=False,
            )

            print(f"[API] Reconstructing timeline for {case_id}")
            timeline = run_reconstruction(
                graph_path=graph_path,
                output_path=timeline_path,
                prefer_neo4j=False,
            )

            print(f"[API] Running rule validation for {case_id}")
            validation = run_validation_pipeline(
                graph_path=graph_path,
                output_dir=validation_dir,
                use_neo4j=False,
            )

            alerts_path = validation_dir / "alerts.json"
            alerts_data = []
            if alerts_path.exists():
                with open(alerts_path, "r", encoding="utf-8") as handle:
                    alerts_data = json.load(handle)
            report_markdown = build_case_report_markdown(
                case_id=case_id,
                case_title=case_data.get("title") or case_id,
                manifest={
                    "staged_sources": {source: Path(path).name for source, path in staged["staged_sources"].items()},
                    "source_processing": source_processing,
                    "unsupported_files": staged["unsupported_files"],
                },
                graph=graph_data,
                timeline=timeline,
                alerts=alerts_data,
            )
            report_path = output_dir / "investigation_report.md"
            report_path.write_text(report_markdown, encoding="utf-8")

            processed_at = __import__("datetime").datetime.now().astimezone().isoformat()
            manifest = {
                "case_id": case_id,
                "status": "success",
                "processed_at": processed_at,
                "staged_sources": {
                    source: Path(path).name for source, path in staged["staged_sources"].items()
                },
                "unsupported_files": staged["unsupported_files"],
                "source_processing": source_processing,
                "report_available": report_path.exists(),
                "entity_count": len(graph_data.get("master_entities", [])),
                "relation_count": len(graph_data.get("relations", [])),
                "timeline_event_count": timeline.get("total_events", 0),
                "timeline_scene_count": timeline.get("total_scenes", 0),
                "unplaced_event_count": timeline.get("unplaced_event_count", 0),
                "validation": validation,
            }
            manifest_path = output_dir / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, ensure_ascii=False)

            return {
                "status": "success",
                "case_id": case_id,
                "message": f"Evidence processing completed for case '{case_id}'.",
                "processed_at": processed_at,
                "processed_sources": sorted(staged["staged_sources"].keys()),
                "unsupported_files": staged["unsupported_files"],
                "source_processing": source_processing,
                "report_available": manifest["report_available"],
                "entity_count": manifest["entity_count"],
                "relation_count": manifest["relation_count"],
                "timeline_event_count": manifest["timeline_event_count"],
                "timeline_scene_count": manifest["timeline_scene_count"],
                "unplaced_event_count": manifest["unplaced_event_count"],
                "validation": validation,
                "results_url": f"/api/cases/{case_id}/results",
            }
        except HTTPException:
            raise
        except Exception as exc:
            print(f"[API] Pipeline execution failed for case {case_id}: {exc}")
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                with open(output_dir / "manifest.json", "w", encoding="utf-8") as handle:
                    json.dump({"case_id": case_id, "status": "failed", "error": str(exc)}, handle)
            except Exception:
                pass
            raise HTTPException(
                status_code=500,
                detail=f"Pipeline execution failed for case '{case_id}': {exc}",
            )


@app.get("/api/cases/{case_id}/results")
def get_case_results(case_id: str):
    """Return graph, summary, timeline and rule outputs from one case workspace."""
    try:
        validate_case_id(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    case_data = db.get_case(case_id=case_id)
    if not case_data:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    case_workspace = CASE_DATA_DIR / case_id
    output_dir = case_workspace / "outputs"
    manifest_path = output_dir / "manifest.json"
    graph_path = output_dir / "unified_graph.json"
    summary_path = output_dir / "summary.json"
    timeline_path = output_dir / "timeline.json"
    validation_dir = output_dir / "validation"

    if not manifest_path.exists() or not graph_path.exists():
        raise HTTPException(status_code=409, detail="This case has not been processed yet.")

    def read_json(path: Path, default):
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    try:
        manifest = read_json(manifest_path, {})
        if manifest.get("status") != "success":
            raise HTTPException(status_code=409, detail="This case has no successfully completed processing run.")
        graph = read_json(graph_path, {"master_entities": [], "relations": []})
        summary = read_json(summary_path, {})
        timeline = read_json(timeline_path, {})
        person_profiles = read_json(validation_dir / "person_risk_profiles.json", [])
        relationship_profiles = read_json(validation_dir / "relationship_risk_profiles.json", [])
        alerts = read_json(validation_dir / "alerts.json", [])

        risk_lookup = {
            profile.get("person_id"): float(profile.get("risk_score", 0.0) or 0.0)
            for profile in person_profiles
            if profile.get("person_id")
        }
        nodes = []
        for entity in graph.get("master_entities", []):
            entity_types = entity.get("entity_types", [])
            is_person = entity.get("master_type") == "PERSON"
            nodes.append({
                "id": entity.get("master_id", ""),
                "label": _entity_label(entity),
                "type": entity.get("master_type", "ENTITY"),
                "sub_type": entity_types[0] if entity_types else "UNKNOWN",
                "risk_score": risk_lookup.get(entity.get("master_id"), 0.0) if is_person else 0.0,
            })

        links = [
            {
                "source": relation.get("source", ""),
                "target": relation.get("target", ""),
                "type": relation.get("relation", "RELATED"),
                "confidence": float(relation.get("confidence", 1.0) or 0.0),
            }
            for relation in graph.get("relations", [])
        ]

        return {
            "case_id": case_id,
            "manifest": manifest,
            "graph": {"nodes": nodes, "links": links},
            "raw_graph": graph,
            "summary": summary,
            "timeline": timeline,
            "person_profiles": person_profiles,
            "relationship_profiles": relationship_profiles,
            "alerts": alerts,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load case results: {exc}")
