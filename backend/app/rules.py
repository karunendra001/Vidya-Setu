"""Tiny rules engine. Rules are JSON, evaluated against form data.
Returns a decision AND a reason for every rule (explainability)."""

OPS = {
    "equals": lambda a, b: a == b,
    "lte":    lambda a, b: a <= b,
    "gte":    lambda a, b: a >= b,
    "in":     lambda a, b: a in b,
}


def evaluate(rules: list[dict], data: dict) -> dict:
    reasons, outcome = [], "ELIGIBLE"
    for r in rules:
        field, op, expected = r["field"], r["operator"], r["value"]
        label = r.get("label", f"{field} {op} {expected}")
        if field not in data or data[field] in (None, ""):
            reasons.append({"rule": label, "passed": None, "why": f"'{field}' not provided"})
            if outcome == "ELIGIBLE":
                outcome = "NEEDS_REVIEW"
            continue
        ok = OPS[op](data[field], expected)
        reasons.append({"rule": label, "passed": ok,
                        "why": f"got {data[field]!r}, expected {op} {expected!r}"})
        if not ok:
            outcome = "NOT_ELIGIBLE"
    return {"result": outcome, "reasons": reasons}


def missing_documents(required: list[str], uploaded: list[str]) -> list[str]:
    return [d for d in required if d not in uploaded]


def required_form_fields(config: dict) -> list[dict]:
    return config.get("form_fields", [])