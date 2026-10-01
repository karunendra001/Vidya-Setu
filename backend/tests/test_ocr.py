from app.ocr_service import compare_field, compare_documents, overall_status

def test_name_fuzzy():
    assert compare_field("name", "Asha Kumari Meena", "ASHA KUMARI MEENA")[0] == "match"
    assert compare_field("name", "Asha Kumari Meena", "Meena Asha Kumari")[0] == "match"
    assert compare_field("name", "Asha Kumari Meena", "Ravi Sharma")[0] == "mismatch"

def test_numeric():
    assert compare_field("pg_percentage", 72.5, "72.5")[0] == "match"
    assert compare_field("pg_percentage", 72.5, "55.0")[0] == "mismatch"
    assert compare_field("family_income", 250000, "2,50,000")[0] == "match"

def test_not_found_and_info():
    assert compare_field("pg_percentage", 72.5, None)[0] == "not_found"
    assert compare_field("certificate_no", None, "ST/1")[0] == "info"

def test_overall():
    ocr = {"fields": {"pg_percentage": "55.0"}, "ocr_conf": 90, "error": None}
    rows = compare_documents([("marksheet", ocr)], {"pg_percentage": 72.5}, "")
    assert overall_status(rows) == "mismatch"

def test_ocr_error_goes_to_review():
    rows = compare_documents([("marksheet", {"error": "boom"})], {}, "")
    assert overall_status(rows) == "review"