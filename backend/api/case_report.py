"""Deterministic, case-scoped report generation from processed evidence outputs."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


def _entity_label(entity: dict[str, Any]) -> str:
    values = entity.get("resolved_values") or []
    if values:
        return str(values[0])
    return str(entity.get("master_id") or "Unknown entity")


def _display(value: Any, fallback: str = "Not recorded") -> str:
    if value is None or value == "":
        return fallback
    return str(value).replace("|", "/").replace("\n", " ")


def _readable_relation(value: Any) -> str:
    raw = str(value or "RELATED")
    return raw.replace("_", " ").strip().title()


def build_case_report_markdown(
    case_id: str,
    case_title: str,
    manifest: dict[str, Any],
    graph: dict[str, Any],
    timeline: dict[str, Any],
    alerts: list[dict[str, Any]] | None = None,
) -> str:
    """Build a reproducible report; no LLM-generated findings or invented metrics."""
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    masters = graph.get("master_entities", []) or []
    relations = graph.get("relations", []) or []
    scenes = timeline.get("scenes", []) or []
    events = [event for scene in scenes for event in (scene.get("events") or [])]
    unplaced = timeline.get("unplaced_events", []) or []
    alerts = alerts or []
    labels = {item.get("master_id"): _entity_label(item) for item in masters}
    total_events = len(events) + len(unplaced)
    timezone_unknown = sum(1 for event in events if event.get("timestamp_status") == "timezone_unknown")
    utc_normalized = sum(1 for event in events if event.get("timestamp_utc"))

    lines = [
        "# TATHYA-DF Investigation Report",
        "",
        f"**Case ID:** {case_id}",
        f"**Case title:** {case_title or case_id}",
        f"**Generated:** {generated_at}",
        "**Report type:** Deterministic summary of the processed case workspace",
        "",
        "> **Investigator review required.** This report summarises parser outputs and rule-based indicators. A graph association is an investigative lead, not proof of identity, presence, intent or guilt. Confirm each material finding against the original evidence and applicable procedures.",
        "",
        "## 1. Processing overview",
        "",
        f"- Evidence files staged: {len(manifest.get('staged_sources', {}))}",
        f"- Entities generated: {len(masters)}",
        f"- Relationships retained: {len(relations)}",
        f"- Total timeline events extracted: {total_events}",
        f"- Events placed into scenes: {len(events)}",
        f"- Unplaced events requiring review: {len(unplaced)}",
        f"- Events with timezone unknown: {timezone_unknown}",
        f"- Events with normalised UTC timestamps: {utc_normalized}",
        f"- Timeline scenes: {len(scenes)}",
        "",
        "**Timeline accounting:** Total extracted events equal placed events plus unplaced events. Events on an unknown source clock are not treated as UTC or globally comparable.",
        "",
        "## 2. Evidence source processing",
        "",
        "| Source category | File | Status | Entities | Relationships | Notes |",
        "|---|---|---|---:|---:|---|",
    ]
    source_rows = manifest.get("source_processing") or []
    if source_rows:
        for source in source_rows:
            lines.append(
                "| {category} | {filename} | {status} | {entities} | {relations} | {note} |".format(
                    category=_display(source.get("category"), "Unknown"),
                    filename=_display(source.get("source_file")),
                    status=_display(source.get("status"), "Unknown"),
                    entities=_display(source.get("entities", 0), "0"),
                    relations=_display(source.get("relations", 0), "0"),
                    note=_display(source.get("error"), "—"),
                )
            )
    else:
        for name, filename in (manifest.get("staged_sources") or {}).items():
            lines.append(f"| {name} | {filename} | Staged; parser status unavailable | — | — | — |")
    unsupported = manifest.get("unsupported_files") or []
    if unsupported:
        lines.extend(["", "**Uploaded but not analysed by an integrated parser:** " + ", ".join(unsupported)])
    lines.extend([
        "",
        "## 3. Knowledge graph overview",
        "",
        "The graph contains the following entity types:",
        "",
    ])
    type_counts: dict[str, int] = {}
    for entity in masters:
        kind = str(entity.get("master_type") or "UNKNOWN")
        type_counts[kind] = type_counts.get(kind, 0) + 1
    if type_counts:
        for kind, count in sorted(type_counts.items()):
            lines.append(f"- {kind.replace('_', ' ').title()}: {count}")
    else:
        lines.append("- No entities were generated.")

    lines.extend([
        "",
        "### Sample retained relationships",
        "",
        "| From entity | Relationship | To entity | Source file | Evidence ID | Record reference |",
        "|---|---|---|---|---|---|",
    ])
    for relation in relations[:20]:
        source_id = relation.get("source")
        target_id = relation.get("target")
        source = labels.get(source_id, source_id or "Unknown entity")
        target = labels.get(target_id, target_id or "Unknown entity")
        lines.append(
            "| {source} | {relation} | {target} | {source_file} | {evidence_id} | {record_id} |".format(
                source=_display(source),
                relation=_readable_relation(relation.get("relation")),
                target=_display(target),
                source_file=_display(relation.get("source_file")),
                evidence_id=_display(relation.get("evidence_id")),
                record_id=_display(relation.get("record_id") or relation.get("artifact_id")),
            )
        )
    if not relations:
        lines.append("| — | No relationships generated | — | — | — | — |")

    lines.extend(["", "## 4. Timeline reconstruction", ""])
    for scene in scenes:
        lines.append(f"### {scene.get('scene_id', 'Scene')} — {scene.get('label', 'Unlabelled scene')}")
        lines.append(f"- Window: {scene.get('window_start', 'unknown')} to {scene.get('window_end', 'unknown')}")
        lines.append(f"- Time basis: {scene.get('time_basis', 'not stated')}")
        lines.append(f"- Timezone status: {scene.get('timezone_status', 'not stated')}")
        for event in (scene.get("events") or [])[:12]:
            lines.append(f"  - {event.get('timestamp', 'Unplaced')}: {event.get('description', 'Event')}")
        lines.append("")
    if unplaced:
        lines.append(f"**Unplaced events requiring review:** {len(unplaced)}")
        for event in unplaced[:10]:
            lines.append(f"- {event.get('description', 'Event without usable timestamp')} — {event.get('source_file') or 'Source not recorded'}")
        lines.append("")

    lines.extend(["## 5. Rule-based indicators", ""])
    if alerts:
        lines.append(f"Rule-based indicators returned: {len(alerts)}. Review each indicator against its rule definition and supporting source records.")
        lines.append("")
        for alert in alerts[:20]:
            name = alert.get("entity_name") or alert.get("entity_id") or "Entity"
            lines.append(
                f"- **{alert.get('description') or alert.get('rule') or 'Indicator'}** for {name}; "
                f"time: {alert.get('timestamp') or 'not recorded'}; "
                f"supporting data: {alert.get('evidence') or 'See the case graph and source record'}."
            )
    else:
        lines.append("No rule-based indicators were returned for this processing run. This does not establish that no suspicious activity occurred.")

    lines.extend(["", "## 6. Evidence traceability samples", ""])
    traceable = [event for event in events if any(event.get(key) for key in ("source_file", "evidence_id", "record_id", "artifact_id", "provenance"))]
    for event in traceable[:15]:
        lines.append(f"### {event.get('description', 'Timeline event')}")
        for key, label in (
            ("source_file", "Source file"),
            ("evidence_id", "Evidence ID"),
            ("evidence_sha256", "Evidence SHA-256"),
            ("source_record_number", "Source record ordinal"),
            ("artifact_id", "Platform artifact reference"),
            ("record_id", "Platform record reference"),
            ("provenance", "Provenance locator"),
            ("provenance_type", "Provenance method"),
        ):
            value = event.get(key)
            if value is not None:
                lines.append(f"- {label}: {value}")
        lines.append("")
    if not traceable:
        lines.append("No event-level source references were available in the timeline output.")

    lines.extend([
        "",
        "## 7. Limitations and interpretation",
        "",
        "- Only evidence categories marked as processed above were analysed by their integrated parser in this run.",
        "- Source-row and platform-generated IDs are trace locators. They do not independently authenticate the originating device, custodian or acquisition process.",
        "- SHA-256 records the digest of the uploaded file as received by this application; it does not prove that the source file was authentic before upload.",
        "- Timestamps without explicit timezone information remain on an unverified source clock and should not be treated as UTC.",
        "- Entity links and rule-based indicators require investigator validation. They must not be interpreted as determinations of guilt.",
        "- This prototype report is for demonstration and analyst review, not a certified forensic report or a substitute for an agency chain-of-custody process.",
        "",
        "## 8. Recommended investigator review",
        "",
        "1. Open each material graph relationship and verify the cited original source record.",
        "2. Confirm device, account and subscriber attribution through authoritative records.",
        "3. Establish source timezone, clock accuracy and acquisition context before cross-source temporal conclusions.",
        "4. Review unsupported uploads, parser failures, conflicting records and missing evidence.",
        "5. Record investigator decisions and independent corroboration separately from automated parser output.",
        "",
    ])
    return "\n".join(lines)



def refresh_case_report_from_outputs(case_id: str, case_title: str, output_dir: str | Path) -> str:
    """Rebuild the saved Markdown report from this case's current persisted outputs.

    This is used by PDF export so an existing case can receive report-layout or
    report-content improvements without re-uploading or reprocessing evidence.
    """
    output_path = Path(output_dir)
    required = {
        "manifest": output_path / "manifest.json",
        "graph": output_path / "unified_graph.json",
        "timeline": output_path / "timeline.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing case outputs: " + ", ".join(missing))

    def read_json(path: Path, default):
        if not path.is_file():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    manifest = read_json(required["manifest"], {})
    if manifest.get("status") != "success":
        raise ValueError("This case does not have a successfully completed processing run.")

    graph = read_json(required["graph"], {"master_entities": [], "relations": []})
    timeline = read_json(required["timeline"], {})
    alerts = read_json(output_path / "validation" / "alerts.json", [])
    report_markdown = build_case_report_markdown(
        case_id=case_id,
        case_title=case_title or case_id,
        manifest=manifest,
        graph=graph,
        timeline=timeline,
        alerts=alerts if isinstance(alerts, list) else [],
    )
    (output_path / "investigation_report.md").write_text(report_markdown, encoding="utf-8")
    return report_markdown
