from datetime import datetime, timedelta
from app.analytics import compute_dashboard

NOW = datetime(2026, 10, 1)


def A(i, status, **fd):
    return {"id": i, "scheme_id": 1, "status": status, "form_data": fd,
            "eligibility_result": "ELIGIBLE", "created_at": NOW - timedelta(days=20)}


def E(i, action, days_ago, actor=9, **detail):
    return {"application_id": i, "action": action, "actor_id": actor,
            "at": NOW - timedelta(days=days_ago), "detail": detail}


def test_funnel_counts():
    apps = [A(1, "DRAFT"), A(2, "SUBMITTED"), A(3, "VERIFIED"), A(4, "SELECTED")]
    d = compute_dashboard(apps, [], {1: "NFST"}, {}, now=NOW)
    assert [f["value"] for f in d["funnel"]] == [4, 3, 2, 1]


def test_processing_time_uses_latest_submit_before_each_decision():
    ev = [E(1, "SUBMIT", 10, actor=1), E(1, "DECISION", 8, decision="DEFICIENT", note="x"),
          E(1, "SUBMIT", 6, actor=1), E(1, "DECISION", 3, decision="VERIFIED")]
    d = compute_dashboard([A(1, "VERIFIED")], ev, {1: "NFST"}, {9: "Off"}, now=NOW)
    assert d["kpis"]["avg_days"] == 2.5          # (2 + 3) / 2
    assert d["kpis"]["deficiency_rate"] == 50.0


def test_reasons_are_grouped_case_insensitively():
    ev = [E(1, "DECISION", 5, decision="DEFICIENT", note="Income certificate unreadable"),
          E(2, "DECISION", 4, decision="REJECTED", note="income certificate UNREADABLE"),
          E(3, "DECISION", 3, decision="REJECTED", note="Not ST")]
    d = compute_dashboard([A(1, "DEFICIENT"), A(2, "REJECTED"), A(3, "REJECTED")], ev,
                          {1: "NFST"}, {9: "Off"}, now=NOW)
    assert d["top_reasons"][0]["value"] == 2
    assert d["by_officer"][0]["REJECTED"] == 2


def test_pending_ageing():
    d = compute_dashboard([A(1, "SUBMITTED")], [E(1, "SUBMIT", 5, actor=1)],
                          {1: "NFST"}, {}, now=NOW)
    assert d["kpis"]["pending"] == 1 and d["kpis"]["oldest_pending_days"] == 5.0