# main.py

import json
import sys
from pathlib import Path

# Ensure imports work regardless of where this script is called from
sys.path.insert(0, str(Path(__file__).parent))

import preprocessed_outputs as preprocess_module
from preprocessed_outputs import (run_all_preprocessors, collect_graph_components, _attach_evidence_provenance)
from entity_resolution import (resolve_entities)
from graph_integrator import (integrate_graph, save_unified_graph)
from investigator_annotations import (load_annotations, build_annotation_relations)

# ------------------------------------------------
# MAIN PIPELINE
# ------------------------------------------------

def main(data_dir=None, output_path=None, vehicle_data_dir=None, source_manifest=None):

    print("\n========== STEP 1 ==========")
    print("RUNNING PREPROCESSORS\n")

    data_dir = Path(data_dir) if data_dir is not None else Path(__file__).parent / "data"
    vehicle_data_dir = Path(vehicle_data_dir) if vehicle_data_dir is not None else Path(__file__).parent.parent / "preprocessor" / "Vehicle_License_preprocessed"
    all_graphs = run_all_preprocessors(data_dir=data_dir, vehicle_data_dir=vehicle_data_dir, source_manifest=source_manifest)

    combined_graph = (collect_graph_components(all_graphs))

    entities = combined_graph["entities"]

    relations = combined_graph["relations"]

    print(f"[INFO] Entities: {len(entities)}")

    print(f"[INFO] Relations: {len(relations)}")

    # ------------------------------------------------
    # BUILD ENTITY LOOKUP
    # ------------------------------------------------

    entity_lookup = {}

    for entity in entities:

        entity_id = (
            entity.get("temp_id")
            or entity.get("id")
        )

        entity_lookup[entity_id] = entity

    # ------------------------------------------------
    # LOAD INVESTIGATOR ANNOTATIONS
    # ------------------------------------------------

    print("\n========== STEP 2 ==========")
    print("LOADING INVESTIGATOR ANNOTATIONS\n")

    annotation_path = data_dir / "annotations.csv"
    if annotation_path.exists():
        try:
            annotations = load_annotations(str(annotation_path))
            annotation_relations = build_annotation_relations(annotations, entity_lookup)
            _attach_evidence_provenance(
                {"entities": [], "relations": annotation_relations},
                "annotations.csv",
                source_manifest,
            )
            preprocess_module.PREPROCESSOR_STATUS.append({
                "category": "annotations",
                "source_file": "annotations.csv",
                "status": "processed",
                "entities": 0,
                "relations": len(annotation_relations),
                "input_records": len(annotations),
                "unmatched_records": max(0, len(annotations) - len(annotation_relations)),
                "error": None,
            })
        except Exception as exc:
            annotations = []
            annotation_relations = []
            preprocess_module.PREPROCESSOR_STATUS.append({
                "category": "annotations",
                "source_file": "annotations.csv",
                "status": "failed",
                "entities": 0,
                "relations": 0,
                "error": str(exc),
            })
            print(f"[WARN] Investigator annotations could not be processed: {exc}")
    else:
        annotations = []
        annotation_relations = []
        preprocess_module.PREPROCESSOR_STATUS.append({
            "category": "annotations",
            "source_file": None,
            "status": "not_supplied",
            "entities": 0,
            "relations": 0,
            "error": None,
        })

    relations.extend(annotation_relations)

    print(
        f"[INFO] Annotation Relations: "
        f"{len(annotation_relations)}"
    )

    print(
        f"[INFO] Updated Relations: "
        f"{len(relations)}"
    )

    # ------------------------------------------------
    # ENTITY RESOLUTION
    # ------------------------------------------------

    print("\n========== STEP 3 ==========")
    print("ENTITY RESOLUTION\n")

    resolution_output = resolve_entities(
        entities,
        relations
    )

    print(
        f"[INFO] Master Entities: "
        f"{len(resolution_output['master_entities'])}"
    )

    # ------------------------------------------------
    # GRAPH INTEGRATION
    # ------------------------------------------------

    print("\n========== STEP 4 ==========")
    print("GRAPH INTEGRATION\n")

    unified_graph = integrate_graph(
        entities,
        relations,
        resolution_output
    )

    print(
        f"[INFO] Final Relations: "
        f"{len(unified_graph['relations'])}"
    )

    # ------------------------------------------------
    # SAVE
    # ------------------------------------------------

    resolved_output_path = Path(output_path) if output_path is not None else Path(__file__).parent / "output" / "unified_graph.json"
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    save_unified_graph(unified_graph, str(resolved_output_path))

    print(
        "\n========== COMPLETE ==========\n"
    )
    return {
        "graph": unified_graph,
        "preprocessor_status": list(preprocess_module.PREPROCESSOR_STATUS),
    }


# ------------------------------------------------
# RUN
# ------------------------------------------------

if __name__ == "__main__":

    main()
