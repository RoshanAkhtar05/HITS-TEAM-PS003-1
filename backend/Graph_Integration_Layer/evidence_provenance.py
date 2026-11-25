"""Utilities for attaching transparent source-evidence references to graph records."""
from __future__ import annotations

import hashlib
from pathlib import Path


def attach_evidence_provenance(graph, default_filename, source_manifest=None):
    """Attach source upload identity and a stable parser-level record locator.

    Platform-generated artifact_id/record_id values are trace references, not
    source-originator IDs and not proof of source authenticity. Provenance is
    preserved as supplied by the parser; otherwise a transparent parser-row or
    relation-index locator is generated.
    """
    source_manifest = source_manifest or {}

    def info_for(record):
        provenance = record.get("provenance")
        provenance_file = None
        if isinstance(provenance, str) and provenance:
            provenance_file = provenance.split(":", 1)[0]
        candidates = (
            record.get("source_file"), provenance_file, record.get("source"), default_filename,
        )
        for candidate in candidates:
            if candidate:
                candidate_name = Path(str(candidate)).name
                if candidate_name in source_manifest:
                    return source_manifest[candidate_name]
        return {}

    def safe_locator(value: str) -> str:
        value = str(value or "record").strip()
        return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:96]

    for kind in ("entities", "relations"):
        for index, record in enumerate(graph.get(kind, []), start=1):
            info = info_for(record)
            original_filename = info.get("original_filename") or default_filename
            evidence_id = info.get("evidence_id")
            file_sha256 = info.get("sha256")

            if original_filename:
                record["source_file"] = original_filename
            if evidence_id is not None:
                record["evidence_id"] = str(evidence_id)
            if file_sha256:
                record["evidence_sha256"] = file_sha256

            if kind != "relations":
                continue

            relation_name = safe_locator(str(record.get("relation") or "RELATED").upper())
            evidence_key = safe_locator(evidence_id if evidence_id is not None else (original_filename or "source"))
            source_record_number = record.get("source_record_number")
            try:
                source_record_number = int(source_record_number) if source_record_number is not None else None
            except (TypeError, ValueError):
                source_record_number = None
            if source_record_number is not None and source_record_number < 1:
                source_record_number = None
            if source_record_number is not None:
                record["source_record_number"] = source_record_number

            existing_provenance = record.get("provenance")
            locator = None
            if isinstance(existing_provenance, str) and existing_provenance:
                prefix, separator, suffix = existing_provenance.partition(":")
                if separator:
                    locator = suffix
                    record["provenance"] = f"{original_filename}:{suffix}"
                else:
                    locator = existing_provenance
                    record["provenance"] = f"{original_filename}:{existing_provenance}"

            if source_record_number is not None:
                locator = f"row:{source_record_number}"
                record.setdefault("provenance", f"{original_filename}:data-row:{source_record_number}")
                record.setdefault("provenance_type", "generated_from_parser_row_number")
            elif locator:
                record.setdefault("provenance_type", "preprocessor_supplied")
            else:
                locator = f"relation:{index}"
                record["provenance"] = f"{original_filename}:relation-index:{index}"
                record.setdefault("provenance_type", "generated_from_relation_index")

            # Keep parser row references human-readable and stable across runs.
            locator_key = f"ROW-{source_record_number:06d}" if source_record_number is not None else safe_locator(locator)
            if not record.get("record_id"):
                record["record_id"] = f"EVIDENCE-{evidence_key}:{locator_key}:REL-{relation_name}:{index:04d}"

            if not record.get("artifact_id"):
                # Relations derived from the same source row/message share one
                # artifact reference, while their record IDs remain distinct.
                file_identity = file_sha256 or evidence_key
                artifact_seed = f"{file_identity}|{locator_key}"
                artifact_digest = hashlib.sha256(artifact_seed.encode("utf-8")).hexdigest()[:16].upper()
                record["artifact_id"] = f"ART-{artifact_digest}"

    return graph
