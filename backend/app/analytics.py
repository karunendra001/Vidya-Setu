"""Dashboard numbers. Pure function: takes plain dicts, so it is easy to test."""
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median

VERIFIED_SET = {"VERIFIED", "SELECTED", "WAITLISTED", "NOT_SELECTED"}


def _days(a, b):
    return max((b - a).total_seconds() / 86400, 0.0)


def _buckets(values, edges, labels):
    out = [0] * len(labels)
    for v in values:
        for i, edge in enumerate(edges):
            if v <= edge:
                out[i] += 1
                break
        else:
            out[-1] += 1
    return [{"name": l, "value": c} for l, c in zip(labels, out)]


def _counts(counter, limit=None):
    rows = [{"name": k, "value": v} for k, v in counter.most_common(limit)]
    return rows


def compute_dashboard(apps, events, scheme_names, user_names, now=None):
    """apps: [{id, scheme_id, status, form_data, eligibility_result, created_at}]
    events: [{application_id, action, actor_id, at, detail}]  (SUBMIT / DECISION only)"""
    now = now or datetime.utcnow()
    events = sorted(events, key=lambda e: e["at"])

    submitted = [a for a in apps if a["status"] != "DRAFT"]
    verified = [a for a in apps if a["status"] in VERIFIED_SET]
    selected = [a for a in apps if a["status"] == "SELECTED"]

    subs = defaultdict(list)
    for e in events:
        if e["action"] == "SUBMIT":
            subs[e["application_id"]].append(e["at"])

    durations, reasons = [], {}
    decisions = Counter()
    per_officer = defaultdict(Counter)
    for e in events:
        if e["action"] != "DECISION":
            continue
        detail = e.get("detail") or {}
        dec = detail.get("decision")
        decisions[dec] += 1
        per_officer[e["actor_id"]][dec] += 1
        prior = [t for t in subs.get(e["application_id"], []) if t <= e["at"]]
        if prior:                                   # time from latest submission to this decision
            durations.append(_days(prior[-1], e["at"]))
        if dec in ("DEFICIENT", "REJECTED"):
            note = (detail.get("note") or "").strip()
            if note:
                reasons.setdefault(note.lower()[:80], [note[:80], 0])[1] += 1

    pending_ages = []
    for a in apps:
        if a["status"] == "SUBMITTED":
            s = subs.get(a["id"])
            pending_ages.append(_days(s[-1] if s else a["created_at"], now))

    by_scheme = []
    for sid, name in scheme_names.items():
        mine = [a for a in apps if a["scheme_id"] == sid]
        if mine:
            by_scheme.append({
                "scheme": name, "started": len(mine),
                "submitted": sum(a["status"] != "DRAFT" for a in mine),
                "verified": sum(a["status"] in VERIFIED_SET for a in mine),
                "selected": sum(a["status"] == "SELECTED" for a in mine)})

    total_dec = sum(decisions.values())
    officers = []
    for uid, c in per_officer.items():
        officers.append({"name": user_names.get(uid, f"User {uid}"), "VERIFIED": c["VERIFIED"],
                         "DEFICIENT": c["DEFICIENT"], "REJECTED": c["REJECTED"]})
    officers.sort(key=lambda o: -(o["VERIFIED"] + o["DEFICIENT"] + o["REJECTED"]))

    return {
        "kpis": {
            "total": len(apps), "submitted": len(submitted), "verified": len(verified),
            "selected": len(selected), "pending": len(pending_ages),
            "avg_days": round(sum(durations) / len(durations), 1) if durations else None,
            "median_days": round(median(durations), 1) if durations else None,
            "deficiency_rate": round(100 * decisions["DEFICIENT"] / total_dec, 1) if total_dec else 0,
            "oldest_pending_days": round(max(pending_ages), 1) if pending_ages else 0,
        },
        "funnel": [{"name": "Started", "value": len(apps)}, {"name": "Submitted", "value": len(submitted)},
                   {"name": "Verified", "value": len(verified)}, {"name": "Selected", "value": len(selected)}],
        "status": _counts(Counter(a["status"] for a in apps)),
        "by_scheme": by_scheme,
        "by_state": _counts(Counter((a["form_data"] or {}).get("state") or "Not recorded"
                                    for a in submitted), 12),
        "by_gender": _counts(Counter((a["form_data"] or {}).get("gender") or "Not recorded"
                                     for a in submitted)),
        "eligibility": _counts(Counter(a.get("eligibility_result") or "UNKNOWN" for a in submitted)),
        "processing_buckets": _buckets(durations, [2, 5, 10], ["Up to 2 days", "3 to 5 days", "6 to 10 days", "Over 10 days"]),
        "ageing": _buckets(pending_ages, [3, 7], ["Under 3 days", "3 to 7 days", "Over 7 days"]),
        "by_officer": officers,
        "top_reasons": [{"name": n, "value": c} for n, c in
                        sorted(reasons.values(), key=lambda x: -x[1])[:8]],
    }