# graph_integrator.py

import json

# ------------------------------------------------
# GRAPH INTEGRATION
# ------------------------------------------------

def integrate_graph(
    entities,
    relations,
    resolution_output
):

    resolved_mapping = (
        resolution_output[
            "resolved_mapping"
        ]
    )

    master_entities = (
        resolution_output[
            "master_entities"
        ]
    )

    # ------------------------------------------------
    # REWRITE RELATIONS
    # ------------------------------------------------

    integrated_relations = []

    seen_relations = set()

    for relation in relations:

        source = relation["source"]

        target = relation["target"]

        relation_type = relation[
            "relation"
        ]

        # ------------------------------------------------
        # MAP TO MASTER IDs
        # ------------------------------------------------

        new_source = resolved_mapping.get(
            source,
            source
        )

        new_target = resolved_mapping.get(
            target,
            target
        )

        # ------------------------------------------------
        # REMOVE SELF LOOPS
        # ------------------------------------------------

        if new_source == new_target:
            continue

        # ------------------------------------------------
        # DEDUPLICATION KEY
        # ------------------------------------------------

        # Include source-record identity in the key. Two independent files may
        # describe the same relationship and both must remain visible as evidence.
        evidence_identity = (
            relation.get("evidence_id")
            or relation.get("artifact_id")
            or relation.get("record_id")
            or relation.get("provenance")
            or relation.get("source_file")
        )
        relation_key = (
            new_source,
            new_target,
            relation_type,
            relation.get("timestamp"),
            evidence_identity if evidence_identity is not None else id(relation),
        )

        if relation_key in seen_relations:
            continue

        seen_relations.add(
            relation_key
        )

        # ------------------------------------------------
        # UPDATE RELATION
        # ------------------------------------------------

        updated_relation = relation.copy()

        updated_relation[
            "source"
        ] = new_source

        updated_relation[
            "target"
        ] = new_target

        integrated_relations.append(
            updated_relation
        )

    # ------------------------------------------------
    # FINAL GRAPH
    # ------------------------------------------------

    unified_graph = {
        "master_entities": master_entities,
        "relations": integrated_relations
    }

    return unified_graph


# ------------------------------------------------
# SAVE FINAL GRAPH
# ------------------------------------------------

def save_unified_graph(
    unified_graph,
    output_path="unified_graph.json"
):

    with open(output_path, "w") as f:

        json.dump(
            unified_graph,
            f,
            indent=4
        )

    print(
        f"[OK] Unified graph saved: "
        f"{output_path}"
    )