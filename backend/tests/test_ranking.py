from app.ranking import score_application, build_ranking


def C(i, score):
    return {"application_id": i, "name": f"A{i}", "score": score, "breakdown": []}


def test_score_breakdown():
    total, bd = score_application({"pg_percentage": 1.0}, {"pg_percentage": 72.5})
    assert total == 72.5 and bd[0]["points"] == 72.5


def test_missing_field_scores_zero():
    assert score_application({"pg_percentage": 1.0}, {})[0] == 0


def test_order_cutoff_and_tiebreak():
    ranked, _ = build_ranking([C(1, 70), C(2, 90), C(3, 90), C(4, 60)], {}, slots=2, waitlist=1)
    assert [r["application_id"] for r in ranked] == [2, 3, 1, 4]
    assert [r["decision"] for r in ranked] == ["SELECTED", "SELECTED", "WAITLISTED", "NOT_SELECTED"]


def test_pin_moves_applicant_and_keeps_reason():
    ov = {3: {"action": "PIN", "rank": 1, "reason": "documented hardship"}}
    ranked, _ = build_ranking([C(1, 90), C(2, 80), C(3, 70)], ov, slots=1, waitlist=0)
    assert [r["application_id"] for r in ranked] == [3, 1, 2]
    assert ranked[0]["decision"] == "SELECTED" and ranked[0]["auto_rank"] == 3
    assert ranked[0]["override"]["reason"] == "documented hardship"


def test_exclude_removes_from_ranking():
    ov = {1: {"action": "EXCLUDE", "rank": None, "reason": "duplicate"}}
    ranked, excluded = build_ranking([C(1, 90), C(2, 80)], ov, slots=1, waitlist=0)
    assert [r["application_id"] for r in ranked] == [2]
    assert excluded[0]["application_id"] == 1