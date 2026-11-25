"""Case-scoped orchestration for the currently integrated evidence preprocessors.

Missing evidence categories are reported as NOT_SUPPLIED and are not attempted.
Each communication file is processed separately so its records keep the correct
source-file provenance. No bundled demo data is substituted for a case upload.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from .evidence_provenance import attach_evidence_provenance as _attach_evidence_provenance
except ImportError:  # legacy script execution adds this folder directly to sys.path
    from evidence_provenance import attach_evidence_provenance as _attach_evidence_provenance

DATA_DIR = Path(__file__).parent / "data"
VEHICLE_DATA_DIR = BACKEND_DIR / "preprocessor" / "Vehicle_License_preprocessed"
PREPROCESSOR_STATUS: list[dict] = []


def _record_status(category: str, filename: str | None, status: str,
                   graph: dict | None = None, error: str | None = None) -> None:
    graph = graph or {"entities": [], "relations": []}
    PREPROCESSOR_STATUS.append({
        "category": category,
        "source_file": filename,
        "status": status,
        "entities": len(graph.get("entities", [])),
        "relations": len(graph.get("relations", [])),
        "error": error,
    })


def _run_file(category: str, path: Path, parser, source_manifest: dict | None,
              graphs: list[dict]) -> None:
    if not path.is_file():
        _record_status(category, None, "not_supplied")
        print(f"[SKIP] {category}: no evidence file supplied")
        return
    try:
        graph = parser(str(path))
        _attach_evidence_provenance(graph, path.name, source_manifest)
        graphs.append(graph)
        _record_status(category, path.name, "processed", graph)
        print(f"[OK] {category} preprocessing completed")
    except Exception as exc:
        _record_status(category, path.name, "failed", error=str(exc))
        print(f"[FAIL] {category} preprocessing failed: {exc}")


def run_all_preprocessors(data_dir=None, vehicle_data_dir=None, source_manifest=None):
    """Run only parsers whose inputs were actually staged for this case.

    The function returns a list of graph fragments for backward compatibility.
    Detailed per-category outcomes are available via PREPROCESSOR_STATUS.
    """
    global PREPROCESSOR_STATUS
    PREPROCESSOR_STATUS = []

    data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    vehicle_data_dir = Path(vehicle_data_dir) if vehicle_data_dir is not None else VEHICLE_DATA_DIR
    graphs: list[dict] = []

    # Imports are intentionally lazy: an absent optional source or optional
    # parser dependency must not prevent other supplied evidence from processing.
    cdr_file = data_dir / "cdr.csv"
    if cdr_file.is_file():
        try:
            from preprocessor.CallDetailsRecord.cdr import preprocess_cdr
            _run_file("cdr", cdr_file, preprocess_cdr, source_manifest, graphs)
        except Exception as exc:
            _record_status("cdr", cdr_file.name, "failed", error=str(exc))
            print(f"[FAIL] cdr parser unavailable: {exc}")
    else:
        _record_status("cdr", None, "not_supplied")

    gps_file = data_dir / "gps.csv"
    if gps_file.is_file():
        try:
            from preprocessor.GPS_Preprocessed.gps import preprocess_gps
            _run_file("gps", gps_file, preprocess_gps, source_manifest, graphs)
        except Exception as exc:
            _record_status("gps", gps_file.name, "failed", error=str(exc))
            print(f"[FAIL] gps parser unavailable: {exc}")
    else:
        _record_status("gps", None, "not_supplied")

    transactions_file = data_dir / "transactions.csv"
    if transactions_file.is_file():
        try:
            from preprocessor.bank_transaction_pipeline.main import preprocess_transaction
            parser = lambda path: preprocess_transaction(path, save_intermediates=False)
            _run_file("transactions", transactions_file, parser, source_manifest, graphs)
        except Exception as exc:
            _record_status("transactions", transactions_file.name, "failed", error=str(exc))
            print(f"[FAIL] transactions parser unavailable: {exc}")
    else:
        _record_status("transactions", None, "not_supplied")

    replay_files = sorted(list(data_dir.glob("incoming_evidence*.json")) + list(data_dir.glob("demo_replay*.json")) + list(data_dir.glob("event_stream*.json")))
    if replay_files:
        try:
            from preprocessor.DemoReplay.replay import preprocess_replay_event_file
            for replay_path in replay_files:
                _run_file("demo_replay", replay_path, preprocess_replay_event_file, source_manifest, graphs)
        except Exception as exc:
            _record_status("demo_replay", None, "failed", error=str(exc))
            print(f"[FAIL] demo replay parser unavailable: {exc}")
    else:
        _record_status("demo_replay", None, "not_supplied")

    fir_file = data_dir / "fir.txt"
    if fir_file.is_file():
        try:
            from preprocessor.FIR_Preprocessed.fir import preprocess_fir
            def parse_fir(path: str):
                return preprocess_fir(Path(path).read_text(encoding="utf-8", errors="replace"))
            _run_file("fir", fir_file, parse_fir, source_manifest, graphs)
        except Exception as exc:
            _record_status("fir", fir_file.name, "failed", error=str(exc))
            print(f"[FAIL] fir parser unavailable: {exc}")
    else:
        _record_status("fir", None, "not_supplied")

    # Process communications one file at a time. Each output graph is attached
    # to its own staged file identity rather than assigning all records to email.
    social_specs = (
        ("emails", data_dir / "emails.txt"),
        ("chat", data_dir / "chat.txt"),
        ("social", data_dir / "social.json"),
    )
    for category, path in social_specs:
        if not path.is_file():
            _record_status(category, None, "not_supplied")
            continue
        try:
            from preprocessor.Chats_Social.main import preprocess_socials
            graph = preprocess_socials([str(path)])
            _attach_evidence_provenance(graph, path.name, source_manifest)
            graphs.append(graph)
            _record_status(category, path.name, "processed", graph)
            print(f"[OK] {category} preprocessing completed")
        except Exception as exc:
            _record_status(category, path.name, "failed", error=str(exc))
            print(f"[FAIL] {category} preprocessing failed: {exc}")

    # Vehicle image OCR is an optional image-based adapter. It is run only if
    # the staged workspace contains an actual data/ image folder.
    vehicle_images_dir = vehicle_data_dir / "data"
    if vehicle_images_dir.is_dir() and any(vehicle_images_dir.glob("*")):
        try:
            from preprocessor.Vehicle_License_preprocessed.vehicle import preprocess_vehicle
            graph = preprocess_vehicle(str(vehicle_data_dir))
            _attach_evidence_provenance(graph, "vehicle_image", source_manifest)
            graphs.append(graph)
            _record_status("vehicle_images", str(vehicle_images_dir), "processed", graph)
        except Exception as exc:
            _record_status("vehicle_images", str(vehicle_images_dir), "failed", error=str(exc))
            print(f"[FAIL] vehicle image preprocessing failed: {exc}")
    else:
        _record_status("vehicle_images", None, "not_supplied")

    if not any(item["status"] == "processed" for item in PREPROCESSOR_STATUS):
        raise RuntimeError("No supplied evidence file was successfully processed by an integrated parser.")

    return graphs


def collect_graph_components(all_graphs):
    all_entities = []
    all_relations = []
    for graph in all_graphs:
        all_entities.extend(graph.get("entities", []))
        all_relations.extend(graph.get("relations", []))
    return {"entities": all_entities, "relations": all_relations}


def save_preprocessed_output(output_data):
    output_path = Path(__file__).parent / "output" / "all_preprocessed_graphs.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)
    print(f"[OK] Saved combined graph data to: {output_path}")


if __name__ == "__main__":
    print("\n========== RUNNING PREPROCESSORS ==========\n")
    all_graphs = run_all_preprocessors()
    combined_graph = collect_graph_components(all_graphs)
    print(f"[INFO] Total preprocessors executed: {len(all_graphs)}")
    print(f"[INFO] Total entities collected: {len(combined_graph['entities'])}")
    print(f"[INFO] Total relations collected: {len(combined_graph['relations'])}")
    save_preprocessed_output(combined_graph)
    print("\n========== PREPROCESSING COMPLETE ==========\n")
