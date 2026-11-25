"""
explanation_builder.py
========================
Generates human-readable, professional forensic explanation narratives
summarizing why a person or relationship was assigned their risk level and score.
"""

from collections import Counter

# Friendly descriptors for each rule code
RULE_DESCRIPTORS = {
    "COMM_EXCESSIVE_CALLING": "excessive daily call volume (> 50 calls/day)",
    "COMM_CALL_BURST": "burst calling activity in narrow 15-minute windows",
    "COMM_HUB": "acting as a communication hub (connecting to > 20 partners)",
    "FIN_MULE_PATTERN": "mule-account behavior (immediate forwarding of incoming funds)",
    "FIN_SMURFING": "structuring transaction flows (smurfing sub-threshold transfers)",
    "FIN_HIGH_VELOCITY": "high-frequency rapid transaction velocity",
    "GPS_SHARED_LOCATION_OBSERVATION": "time-proximate shared location observation with another recorded entity; context requires review",
    "GPS_FREQUENT_VISITS": "frequent repeated visits to key tactical locations",
    "COMM_DELETION_LANGUAGE": "exchanging messages containing explicit deletion instructions",
    "COMM_MONEY_REQUEST": "exchanging communications referring to transfers, cash, or withdrawals",
    "TEMP_COMM_TO_TRANSFER": "coordinated communication followed immediately by financial transfer",
    "TEMP_COLOCATION_TO_TRANSFER": "physical meetings followed immediately by money movement",
    "TEMP_EMAIL_CALL_TRANSFER": "coordinated email-to-call-to-transfer operational chains",
}

def build_person_explanation(name: str, score: float, level: str, evidence: list, confidence: float) -> str:
    """
    Generates a natural-language narrative for a person's risk profile.
    """
    if not evidence:
        return f"No configured rule-based indicators were generated for {name} in this case run. This is not evidence that no relevant activity occurred."
        
    # Count rules triggered
    rule_counts = Counter(e["rule_code"] for e in evidence)
    
    # Sort rules by weighted contribution descending
    sorted_evidence = sorted(evidence, key=lambda x: x["weighted_contribution"], reverse=True)
    
    # Get top 3 factors
    top_factors = []
    seen_codes = set()
    for e in sorted_evidence:
        code = e["rule_code"]
        if code not in seen_codes:
            seen_codes.add(code)
            descriptor = RULE_DESCRIPTORS.get(code, e["rule_name"].lower())
            top_factors.append(descriptor)
            if len(top_factors) >= 3:
                break
                
    factors_str = ""
    if len(top_factors) == 1:
        factors_str = top_factors[0]
    elif len(top_factors) == 2:
        factors_str = f"{top_factors[0]} and {top_factors[1]}"
    else:
        factors_str = f"{top_factors[0]}, {top_factors[1]}, and {top_factors[2]}"
        
    confidence_pct = int(confidence * 100)
    
    narrative = (
        f"{name} has a rule-indicator score of {score} in the {level} band (engine confidence field: {confidence_pct}%). "
        f"The primary contributing factors include: {factors_str}. "
    )
    
    # Add extra context if mule account or deletion language is detected
    has_mule = any(e["rule_code"] == "FIN_MULE_PATTERN" for e in evidence)
    has_delete = any(e["rule_code"] == "COMM_DELETION_LANGUAGE" for e in evidence)
    
    if has_mule and has_delete:
        narrative += (
            "The combination of fund-forwarding patterns and deletion-related language "
            "may warrant review. These indicators do not establish intent or wrongdoing."
        )
    elif has_mule:
        narrative += "The observed transfer sequence may warrant account-flow review and independent corroboration."
    elif has_delete:
        narrative += "Deletion-related language is present in the communication record; its context and meaning require investigator review."
        
    return narrative

def build_relationship_explanation(profile: dict) -> str:
    """
    Generates a natural-language narrative for a relationship profile.
    """
    ent1 = profile["entity_1"]
    ent2 = profile["entity_2"]
    score = profile["risk_score"]
    level = profile["risk_level"]
    ev_list = profile["supporting_evidence"]
    
    if not ev_list:
        return f"No configured relationship indicators were generated for {ent1} and {ent2}; this does not establish the absence of a relevant relationship."
        
    evidence_str = "; ".join(ev_list)
    return (
        f"The connection between {ent1} and {ent2} has a rule-indicator score of {score} in the {level} band. "
        f"Supporting indicators: {evidence_str}. This is an investigative lead, not a finding of guilt."
    )
