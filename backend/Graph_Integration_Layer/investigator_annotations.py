# investigator_annotations.py

import csv
import uuid

# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def generate_annotation_id():
    return f"ANNOT_{uuid.uuid4().hex[:8]}"


# ------------------------------------------------
# LOAD ANNOTATIONS
# ------------------------------------------------

def load_annotations(annotation_path):

    annotations = []

    with open(annotation_path, "r", newline="", encoding="utf-8") as f:

        reader = csv.DictReader(f)
        
        if reader.fieldnames is None:
            raise ValueError(
                f"CSV file at '{annotation_path}' is empty or invalid."
            )
            
        # Normalize and clean actual headers
        clean_fieldnames = [name.strip().lower() for name in reader.fieldnames if name]
        
        # Verify required headers exist
        required_headers = ["source_entity", "target_entity", "relation"]
        missing = [req for req in required_headers if req not in clean_fieldnames]
        
        if missing:
            raise ValueError(
                f"\n[ERROR] CSV Headings Mismatch in '{annotation_path}'!\n"
                f"Expected headings: {', '.join(required_headers)}\n"
                f"Missing required headings: {', '.join(missing)}\n"
                f"Detected headings in your CSV: {', '.join(reader.fieldnames)}\n"
                f"Please check your CSV headers and try again.\n"
            )

        for source_record_number, row in enumerate(reader, start=1):
            # Re-key row using standardized lowercase and stripped keys
            clean_row = {"_source_record_number": source_record_number}
            for k, v in row.items():
                if k:
                    clean_row[k.strip().lower()] = v

            # Parse confidence
            confidence_val = clean_row.get("confidence")
            if confidence_val:
                try:
                    clean_row["confidence"] = float(confidence_val)
                except ValueError:
                    clean_row["confidence"] = 0.95
            else:
                clean_row["confidence"] = 0.95

            # Set evidence default if not present
            if "evidence" not in clean_row:
                clean_row["evidence"] = "investigator_annotation"

            annotations.append(clean_row)

    return annotations


# ------------------------------------------------
# BUILD ANNOTATION RELATIONS
# ------------------------------------------------

def build_annotation_relations(annotations, entity_lookup):
    """Build investigator-supplied links from exact, type-constrained matches.

    Duplicate parser nodes with the same type/value are expected before entity
    resolution, so one deterministic representative is selected. Cross-type or
    ambiguous values are not guessed. No network geocoding is performed.
    """
    import re

    relations = []

    def norm(value):
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    def expected_types(value):
        value_norm = norm(value)
        if "@" in value_norm:
            return {"PERSON", "EMAIL"}
        digits = re.sub(r"\D", "", value_norm)
        if len(digits) >= 8 and len(digits) <= 15 and digits == value_norm:
            return {"PHONE_NUMBER"}
        if value_norm.startswith("acc"):
            return {"ACCOUNT"}
        if value_norm.startswith(("android", "iphone", "pixel", "device")):
            return {"DEVICE"}
        if value_norm.startswith("watch"):
            return {"WEARABLE_DEVICE", "DEVICE"}
        if value_norm.startswith(("tracker", "gps")):
            return {"TRACKER", "DEVICE"}
        if re.fullmatch(r"-?\d+(?:\.\d+)?", value_norm):
            return {"LOCATION"}
        if any(token in value_norm for token in ("street", "station", "road", "kolkata", "howrah")):
            return {"LOCATION"}
        return {"PERSON"}

    def exact_matches(value):
        target = norm(value)
        allowed = expected_types(value)
        found = []
        for entity_id, entity in entity_lookup.items():
            entity_type = str(entity.get("type") or "").upper()
            if entity_type not in allowed:
                continue
            attrs = entity.get("attributes") or {}
            candidates = []
            if entity_type == "PERSON":
                candidates.extend([attrs.get("name"), attrs.get("email")])
            elif entity_type == "PHONE_NUMBER":
                candidates.extend([attrs.get("number"), attrs.get("identifier")])
            elif entity_type == "EMAIL":
                candidates.append(attrs.get("email"))
            elif entity_type in {"DEVICE", "WEARABLE_DEVICE", "TRACKER"}:
                candidates.extend([attrs.get("identifier"), attrs.get("name")])
            elif entity_type == "ACCOUNT":
                candidates.extend([attrs.get("account_id"), entity.get("temp_id"), entity.get("id")])
            elif entity_type == "LOCATION":
                name = norm(attrs.get("name"))
                if name and (name == target or name.startswith(target + ",")):
                    found.append((entity_id, entity_type))
                lat, lon = attrs.get("latitude"), attrs.get("longitude")
                if target and lat is not None and lon is not None:
                    try:
                        if abs(float(target) - float(lat)) < 0.00001:
                            found.append((entity_id, entity_type))
                        elif "," in target:
                            target_lat, target_lon = target.split(",", 1)
                            if abs(float(target_lat) - float(lat)) < 0.00001 and abs(float(target_lon) - float(lon)) < 0.00001:
                                found.append((entity_id, entity_type))
                    except (TypeError, ValueError):
                        pass
            if any(norm(candidate) == target for candidate in candidates if candidate is not None):
                found.append((entity_id, entity_type))

        unique = sorted(set(found), key=lambda item: (item[1], item[0]))
        matching_types = {item[1] for item in unique}
        if len(matching_types) != 1:
            return []
        # Same-type duplicate nodes will be merged by the typed resolver.
        return [unique[0][0]] if unique else []

    for annotation in annotations:
        source_matches = exact_matches(annotation.get("source_entity", ""))
        target_matches = exact_matches(annotation.get("target_entity", ""))
        if len(source_matches) != 1 or len(target_matches) != 1:
            continue
        source_id, target_id = source_matches[0], target_matches[0]
        if source_id == target_id:
            continue
        source_record_number = annotation.get("_source_record_number")
        relations.append({
            "annotation_id": generate_annotation_id(),
            "source": source_id,
            "target": target_id,
            "relation": annotation.get("relation", "RELATED"),
            "attributes": {
                "evidence": annotation.get("evidence", "investigator_annotation"),
                "assertion_type": "investigator_supplied_annotation",
            },
            "confidence": annotation.get("confidence", 0.95),
            "source_type": "investigator_annotation",
            "source_record_number": source_record_number,
            "provenance": f"annotations.csv:data-row:{source_record_number or 'unknown'}",
        })
    return relations
