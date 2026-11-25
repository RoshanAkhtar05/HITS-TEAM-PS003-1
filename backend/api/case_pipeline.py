"""Case-scoped evidence staging helpers for the local TATHYA-DF pipeline."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# The prototype's integrated preprocessing layer currently accepts one file for
# each canonical source category. Other uploaded formats remain preserved in the
# evidence vault but are not silently misclassified as parser inputs.
SOURCE_RULES = (
    ("fir", ("fir", "first_information_report"), {"txt"}, "fir.txt"),
    ("cdr", ("cdr", "call_detail", "call-details", "call_records", "callrecord"), {"csv"}, "cdr.csv"),
    ("gps", ("gps", "location", "geolocation"), {"csv"}, "gps.csv"),
    ("transactions", ("bank", "transaction", "transfer", "statement"), {"csv"}, "transactions.csv"),
    ("emails", ("email", "mail"), {"txt"}, "emails.txt"),
    ("chat", ("chat", "whatsapp", "telegram", "message", "messages"), {"txt"}, "chat.txt"),
    ("social", ("social", "instagram", "facebook", "social_media"), {"json"}, "social.json"),
    ("annotations", ("annotation", "investigator_note"), {"csv"}, "annotations.csv"),
    ("demo_replay", ("incoming_evidence", "demo_replay", "event_stream"), {"json"}, None),
    ("vehicle_images", ("vehicle", "plate", "registration", "number_plate", "car_photo", "bike_photo"), {"jpg", "jpeg", "png"}, None),
)


def validate_case_id(case_id: str) -> str:
    """Validate case IDs before using them in filesystem paths."""
    if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("Invalid case ID. Use 1–64 letters, numbers, underscores or hyphens.")
    return case_id


def classify_evidence_file(file_path: Path) -> tuple[str, str] | None:
    """Return (source category, canonical filename) for supported parser inputs."""
    suffix = file_path.suffix.lower().lstrip(".")
    filename = file_path.stem.lower()
    for category, tokens, allowed_extensions, canonical_name in SOURCE_RULES:
        if suffix in allowed_extensions and any(token in filename for token in tokens):
            return category, canonical_name
    return None


def stage_case_inputs(upload_dir: Path, workspace_dir: Path, evidence_records=None) -> dict:
    """Copy recognised evidence into a clean, case-specific parser workspace.

    Original uploaded files are never changed. Unrecognised files are returned
    explicitly so the UI/API can distinguish uploaded from currently processable
    evidence.
    """
    upload_dir = Path(upload_dir)
    workspace_dir = Path(workspace_dir)
    input_dir = workspace_dir / "inputs"
    vehicle_dir = workspace_dir / "vehicle_input"

    if not upload_dir.is_dir():
        raise FileNotFoundError("No uploaded evidence directory exists for this case.")

    if input_dir.exists():
        shutil.rmtree(input_dir)
    if vehicle_dir.exists():
        shutil.rmtree(vehicle_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    vehicle_dir.mkdir(parents=True, exist_ok=True)

    staged: dict[str, str] = {}
    source_manifest: dict[str, dict] = {}
    # Evidence records are returned newest-first. Preserve the first record
    # for each filename so a re-upload uses its current evidence ID and hash.
    evidence_by_filename = {}
    for item in (evidence_records or []):
        filename = item.get("filename")
        if filename and filename not in evidence_by_filename:
            evidence_by_filename[filename] = item
    unsupported: list[str] = []
    collisions: dict[str, list[str]] = {}
    vehicle_image_count = 0
    replay_file_count = 0

    for file_path in sorted(upload_dir.iterdir()):
        if not file_path.is_file():
            continue
        classification = classify_evidence_file(file_path)
        if classification is None:
            unsupported.append(file_path.name)
            continue

        category, canonical_name = classification
        evidence = evidence_by_filename.get(file_path.name, {})

        # Multiple separately uploaded vehicle images are valid inputs to the
        # image OCR adapter; they are not duplicate source-category collisions.
        if category == "demo_replay":
            replay_file_count += 1
            target_path = input_dir / file_path.name
            shutil.copy2(file_path, target_path)
            staged[f"demo_replay_{replay_file_count:03d}"] = str(target_path)
            source_manifest[file_path.name] = {
                "original_filename": file_path.name,
                "evidence_id": evidence.get("id"),
                "sha256": evidence.get("file_hash"),
            }
            continue

        if category == "vehicle_images":
            vehicle_image_count += 1
            target_dir = vehicle_dir / "data"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / file_path.name
            shutil.copy2(file_path, target_path)
            staged[f"vehicle_image_{vehicle_image_count:02d}"] = str(target_path)
            source_manifest[file_path.name] = {
                "original_filename": file_path.name,
                "evidence_id": evidence.get("id"),
                "sha256": evidence.get("file_hash"),
            }
            continue

        if category in staged:
            collisions.setdefault(category, [Path(staged[category]).name]).append(file_path.name)
            continue

        target_path = input_dir / canonical_name
        shutil.copy2(file_path, target_path)
        staged[category] = str(target_path)
        source_manifest[canonical_name] = {
            "original_filename": file_path.name,
            "evidence_id": evidence.get("id"),
            "sha256": evidence.get("file_hash"),
        }

    if collisions:
        shutil.rmtree(input_dir, ignore_errors=True)
        shutil.rmtree(vehicle_dir, ignore_errors=True)
        details = "; ".join(f"{kind}: {', '.join(names)}" for kind, names in sorted(collisions.items()))
        raise ValueError(
            "More than one uploaded file matches a supported source category. "
            "Combine each source category into one file for this prototype run. " + details
        )

    if not staged:
        shutil.rmtree(input_dir, ignore_errors=True)
        shutil.rmtree(vehicle_dir, ignore_errors=True)
        raise ValueError(
            "No uploaded files matched the currently integrated evidence parsers. "
            "Supported named inputs: FIR TXT, CDR CSV, GPS CSV, bank/transaction CSV, "
            "email TXT, chat TXT, social JSON, investigator annotation CSV, incoming-evidence replay JSON, "
            "and named vehicle/plate images."
        )

    return {
        "input_dir": str(input_dir),
        "vehicle_input_dir": str(vehicle_dir),
        "staged_sources": staged,
        "source_manifest": source_manifest,
        "unsupported_files": unsupported,
    }
