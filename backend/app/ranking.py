"""Explainable merit ranking. Pure functions: no database access."""


def score_application(scoring: dict, form_data: dict):
    """scoring = {field: weight}. Returns (total, per-field breakdown)."""
    breakdown, total = [], 0.0
    for field, weight in scoring.items():
        try:
            value = float(form_data.get(field))
        except (TypeError, ValueError):
            value = 0.0            # missing or non-numeric earns no points
        points = round(value * weight, 2)
        breakdown.append({"field": field, "value": value, "weight": weight, "points": points})
        total += points
    return round(total, 2), breakdown


def build_ranking(cands, overrides, slots, waitlist=0):
    """cands: [{application_id, name, score, breakdown, ...}]
    overrides: {application_id: {action, rank, reason}}
    Returns (ranked, excluded). Each ranked row gets rank, auto_rank, decision, override."""
    def ov(c):
        return overrides.get(c["application_id"])

    excluded = [{**c, "override": ov(c)} for c in cands if ov(c) and ov(c)["action"] == "EXCLUDE"]
    active = [dict(c) for c in cands if not (ov(c) and ov(c)["action"] == "EXCLUDE")]

    # score high to low; tie-break: earlier application first (replace with official rule)
    active.sort(key=lambda c: (-c["score"], c["application_id"]))
    for i, c in enumerate(active, 1):
        c["auto_rank"] = i

    pinned = sorted([c for c in active if ov(c) and ov(c)["action"] == "PIN"],
                    key=lambda c: ov(c)["rank"])
    ordered = [c for c in active if c not in pinned]
    for c in pinned:
        ordered.insert(min(ov(c)["rank"] - 1, len(ordered)), c)

    ranked = []
    for pos, c in enumerate(ordered, 1):
        decision = ("SELECTED" if pos <= slots
                    else "WAITLISTED" if pos <= slots + waitlist else "NOT_SELECTED")
        ranked.append({**c, "rank": pos, "decision": decision, "override": ov(c)})
    return ranked, excluded