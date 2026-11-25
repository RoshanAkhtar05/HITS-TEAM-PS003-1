import spacy
import uuid
import json
try:
    import dateparser
except ImportError:  # Optional enhancement; structured parsing must still work.
    dateparser = None

try:
    nlp = spacy.load("en_core_web_sm")
    NLP_MODEL_MODE = "en_core_web_sm"
except OSError:
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    NLP_MODEL_MODE = "structured_regex_fallback"

# ------------------------------------------------
# RELATION VERB MAP
# ------------------------------------------------

RELATION_VERBS = {
    "meet": "INTERACTED_WITH",
    "call": "CALLED",
    "transfer": "TRANSFERRED_MONEY",
    "visit": "VISITED"
}

# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def generate_temp_id(prefix="TEMP"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def extract_timestamp(sentence):

    for ent in sentence.ents:

        if ent.label_ in ["TIME", "DATE"]:

            if dateparser is not None:
                parsed = dateparser.parse(ent.text)
            else:
                try:
                    from dateutil import parser as dateutil_parser
                    parsed = dateutil_parser.parse(ent.text, fuzzy=True)
                except (ImportError, ValueError, TypeError, OverflowError):
                    parsed = None

            if parsed:
                return parsed.isoformat()

    return None


def get_entity_text(token):
    for ent in token.doc.ents:
        if token.i >= ent.start and token.i < ent.end:
            return ent.text
    return token.text



def _preprocess_fir_structured_fallback(text: str) -> dict:
    """Conservative fallback when spaCy NER is unavailable.

    Extracts only explicitly labelled names and identifiers from numbered
    persons-referenced entries. It does not infer free-text relationships or guilt.
    """
    import re

    entities = []
    relations = []
    id_by_value = {}

    def add_entity(value: str, entity_type: str, attrs: dict):
        key = (entity_type, value.strip().lower())
        if key not in id_by_value:
            temp_id = generate_temp_id(entity_type)
            id_by_value[key] = temp_id
            entities.append({
                "temp_id": temp_id,
                "type": entity_type,
                "attributes": attrs,
                "confidence": 0.75,
                "source": "fir_structured_fallback",
            })
        return id_by_value[key]

    # Numbered entries under a neutral persons-referenced section provide explicit names.
    persons_section = re.search(
        r"(?:Accused persons|Persons referenced(?: in supplied scenario materials)?):\s*(.*?)(?:\n(?:Key locations|Reported locations):|\nCharges:|\nLegal classification:|$)",
        text, flags=re.IGNORECASE | re.DOTALL,
    )
    if persons_section:
        entries = re.finditer(
            r"(?:^|\n)\s*\d+\.\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})\s*[—-]([^\n]+)",
            persons_section.group(1),
        )
        for idx, match in enumerate(entries, start=1):
            person_name, detail = match.groups()
            person_id = add_entity(person_name, "PERSON", {"name": person_name})
            identifiers = []
            identifiers.extend(("PHONE_NUMBER", v, {"number": v}) for v in re.findall(r"(?<!\d)\d{10}(?!\d)", detail))
            identifiers.extend(("ACCOUNT", v, {"account_id": v}) for v in re.findall(r"\bACC[A-Z0-9_-]+\b", detail))
            identifiers.extend(("DEVICE", v, {"identifier": v}) for v in re.findall(r"\b(?:ANDROID|IPHONE|PIXEL|WATCH|DEVICE)[A-Z0-9_-]+\b", detail))
            for entity_type, value, attrs in identifiers:
                target_id = add_entity(value, entity_type, attrs)
                rel_type = "USES_PHONE" if entity_type == "PHONE_NUMBER" else "OWNS_ACCOUNT" if entity_type == "ACCOUNT" else "USES_DEVICE"
                relations.append({
                    "source": person_id,
                    "target": target_id,
                    "relation": rel_type,
                    "attributes": {"extraction_method": "labelled_fir_fallback"},
                    "timestamp": None,
                    "confidence": 0.75,
                    "source_type": "fir_structured_fallback",
                    "source_record_number": idx,
                    "provenance": f"fir.txt:persons-referenced-entry-{idx}",
                })

    # Capture the named police-station/location field as a reported location.
    station_match = re.search(r"Police Station:\s*([^\n]+)", text, flags=re.IGNORECASE)
    if station_match:
        location = station_match.group(1).strip()
        add_entity(location, "LOCATION", {"name": location})

    return {"entities": entities, "relations": relations}

# ------------------------------------------------
# MAIN PREPROCESSOR
# ------------------------------------------------

def preprocess_fir(text):

    # Prefer deterministic extraction from explicitly labelled, numbered
    # person-reference sections when present. This produces the same output
    # whether or not an optional spaCy model is installed on the host machine.
    import re
    has_labelled_people = re.search(
        r"(?:Accused persons|Persons referenced(?: in supplied scenario materials)?):",
        text, flags=re.IGNORECASE,
    ) is not None
    if has_labelled_people or NLP_MODEL_MODE == "structured_regex_fallback":
        return _preprocess_fir_structured_fallback(text)

    doc = nlp(text)

    entities = []
    relations = []

    entity_lookup = {}

    # ------------------------------------------------
    # STEP 1 — EXTRACT LOCATIONS FIRST
    # ------------------------------------------------

    location_tokens = set()

    for ent in doc.ents:

        if ent.label_ in ["GPE", "LOC", "FAC"]:

            temp_id = generate_temp_id()

            entity_obj = {
                "temp_id": temp_id,
                "type": "LOCATION",
                "attributes": {
                    "name": ent.text
                },
                "confidence": 0.90,
                "source": "fir_document"
            }

            entities.append(entity_obj)

            entity_lookup[ent.text] = entity_obj

            # Store location tokens
            for token in ent:
                location_tokens.add(token.text)

    # ------------------------------------------------
    # STEP 2 — EXTRACT PERSONS
    # ------------------------------------------------

    for ent in doc.ents:

        # Only NER-recognized PERSON entities
        if ent.label_ == "PERSON":

            entity_name = ent.text

            if entity_name not in entity_lookup:

                temp_id = generate_temp_id()

                entity_obj = {
                    "temp_id": temp_id,
                    "type": "PERSON",
                    "attributes": {
                        "name": entity_name
                    },
                    "confidence": 0.90,
                    "source": "fir_document"
                }

                entities.append(entity_obj)

                entity_lookup[entity_name] = entity_obj

    # ------------------------------------------------
    # STEP 3 — RELATION EXTRACTION
    # ------------------------------------------------

    for sentence in doc.sents:

        subject = None
        obj = None
        relation_type = None

        timestamp = extract_timestamp(sentence)

        for token in sentence:

            # Detect relation verb
            if token.lemma_.lower() in RELATION_VERBS:

                relation_type = RELATION_VERBS[token.lemma_.lower()]

                # Dependency parsing
                for child in token.children:

                    # Subject
                    if child.dep_ == "nsubj":

                        subject = get_entity_text(child)

                    # Object
                    elif child.dep_ in ["dobj", "pobj", "obj"]:

                        obj = get_entity_text(child)

        # ------------------------------------------------
        # BUILD RELATION OBJECT
        # ------------------------------------------------

        if (
            subject in entity_lookup
            and obj in entity_lookup
            and relation_type
        ):

            source_entity = entity_lookup[subject]
            target_entity = entity_lookup[obj]

            relation_obj = {
                "source": source_entity["temp_id"],
                "target": target_entity["temp_id"],
                "relation": relation_type,
                "attributes": {},
                "timestamp": timestamp,
                "confidence": 0.75,
                "source_type": "fir_document"
            }

            relations.append(relation_obj)

    # ------------------------------------------------
    # FINAL OUTPUT
    # ------------------------------------------------

    output = {
        "entities": entities,
        "relations": relations
    }

    return output



# ------------------------------------------------
# RUN
# ------------------------------------------------

import json
import os

if __name__ == "__main__":

    
    with open("fir_data.txt", "r") as f:
        fir_text = f.read()

    graph_objects = preprocess_fir(fir_text)
    
    # Save to current working directory
    output_path = os.path.join(os.getcwd(), "graph_objects.json")
    
    with open(output_path, 'w') as f:
        json.dump(graph_objects, f, indent=4)
    
    print(f"JSON saved to: {output_path}")