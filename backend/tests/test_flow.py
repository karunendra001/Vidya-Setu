import os, io, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.dirname(__file__)))
os.environ["DATABASE_URL"] = "sqlite:///./test_mota.db"
if os.path.exists("test_mota.db"):
    os.remove("test_mota.db")

from fastapi.testclient import TestClient
import seed
from app.main import app

seed.run()
c = TestClient(app)


def H(tok): return {"Authorization": f"Bearer {tok}"}


def test_full_loop():
    tok = c.post("/auth/register", json={"email": "s@x.com", "password": "pw12345"}).json()["token"]
    scheme = c.get("/schemes").json()[0]
    aid = c.post("/applications", headers=H(tok), json={"scheme_id": scheme["id"]}).json()["id"]

    c.put(f"/applications/{aid}", headers=H(tok),
          json={"category": "ST", "family_income": 300000, "enrolled_in_phd": True, "pg_percentage": 72})

    # submitting without documents must fail
    r = c.post(f"/applications/{aid}/submit", headers=H(tok))
    assert r.status_code == 400 and "caste_certificate" in r.json()["detail"]["missing"]

    for d in ["caste_certificate", "income_certificate", "admission_proof", "marksheet"]:
        c.post(f"/applications/{aid}/documents?doc_type={d}", headers=H(tok),
               files={"file": (f"{d}.pdf", io.BytesIO(b"x"))})

    r = c.post(f"/applications/{aid}/submit", headers=H(tok)).json()
    assert r["eligibility"]["result"] == "NEEDS_REVIEW"

    off = c.post("/auth/login", json={"email": "officer@mota.test", "password": "password123"}).json()["token"]
    assert any(q["id"] == aid for q in c.get("/officer/queue", headers=H(off)).json())

    # officer flags deficiency
    c.post(f"/officer/applications/{aid}/decision", headers=H(off),
           json={"decision": "DEFICIENT", "note": "Income certificate is blurry"})
    mine = c.get("/applications/mine", headers=H(tok)).json()[0]
    assert mine["status"] == "DEFICIENT" and "blurry" in mine["officer_note"]

    # applicant fixes and resubmits
    assert c.post(f"/applications/{aid}/submit", headers=H(tok)).json()["status"] == "SUBMITTED"


def test_ineligible_and_role_guard():
    tok = c.post("/auth/register", json={"email": "t@x.com", "password": "pw12345"}).json()["token"]
    assert c.get("/officer/queue", headers=H(tok)).status_code == 403


def _submitted_app(email):
    tok = c.post("/auth/register", json={"email": email, "password": "pw12345", "full_name": "Asha"}).json()["token"]
    sid = c.get("/schemes").json()[0]["id"]
    aid = c.post("/applications", headers=H(tok), json={"scheme_id": sid}).json()["id"]
    c.put(f"/applications/{aid}", headers=H(tok),
          json={"category": "ST", "family_income": 300000, "enrolled_in_phd": True, "pg_percentage": 72})
    for d in ["caste_certificate", "income_certificate", "admission_proof", "marksheet"]:
        c.post(f"/applications/{aid}/documents?doc_type={d}", headers=H(tok),
               files={"file": (f"{d}.pdf", io.BytesIO(b"%PDF-secret"))})
    c.post(f"/applications/{aid}/submit", headers=H(tok))
    return tok, aid


def test_me_cors_detail_and_downloads():
    tok, aid = _submitted_app("d@x.com")
    me = c.get("/me", headers=H(tok)).json()
    assert me["role"] == "applicant" and me["full_name"] == "Asha"

    r = c.options("/me", headers={"Origin": "http://localhost:5173",
                                  "Access-Control-Request-Method": "GET",
                                  "Access-Control-Request-Headers": "authorization"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"

    d = c.get(f"/applications/{aid}", headers=H(tok)).json()
    assert d["status"] == "SUBMITTED" and d["form_data"]["category"] == "ST"
    assert len(d["documents"]) == 4 and d["missing_documents"] == [] and not d["editable"]
    assert c.get("/applications/mine", headers=H(tok)).status_code == 200

    doc_id = d["documents"][0]["id"]
    assert c.get(f"/documents/{doc_id}/download", headers=H(tok)).content == b"%PDF-secret"

    off = c.post("/auth/login", json={"email": "officer@mota.test", "password": "password123"}).json()["token"]
    assert c.get(f"/documents/{doc_id}/download", headers=H(off)).status_code == 200
    assert c.get(f"/applications/{aid}", headers=H(off)).json()["applicant"]["full_name"] == "Asha"

    # another applicant must not see or download it
    other = c.post("/auth/register", json={"email": "o@x.com", "password": "pw12345"}).json()["token"]
    assert c.get(f"/applications/{aid}", headers=H(other)).status_code == 404
    assert c.get(f"/documents/{doc_id}/download", headers=H(other)).status_code == 404
    assert c.get(f"/documents/{doc_id}/download").status_code in (401, 403)


def test_upload_hardening():
    tok = c.post("/auth/register", json={"email": "u@x.com", "password": "pw12345"}).json()["token"]
    sid = c.get("/schemes").json()[0]["id"]
    aid = c.post("/applications", headers=H(tok), json={"scheme_id": sid}).json()["id"]
    up = lambda q, name, data=b"x": c.post(f"/applications/{aid}/documents?doc_type={q}", headers=H(tok),
                                           files={"file": (name, io.BytesIO(data))})
    assert up("caste_certificate", "x.exe").status_code == 400
    assert up("../../evil", "x.pdf").status_code == 400
    assert up("caste_certificate", "x.pdf", b"a" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert up("caste_certificate", "a.pdf").status_code == 200
    assert up("caste_certificate", "b.pdf").status_code == 200   # replaces
    docs = c.get(f"/applications/{aid}", headers=H(tok)).json()["documents"]
    assert len(docs) == 1 and docs[0]["filename"] == "b.pdf"

def test_clean_documents_stay_eligible(monkeypatch):
    # Pretend OCR read every document correctly and the values match the form.
    fake = {
        "caste_certificate": {"name": "Test User", "category": "ST", "certificate_no": "ST/1"},
        "income_certificate": {"name": "Test User", "family_income": "300000"},
        "marksheet": {"name": "Test User", "pg_percentage": "72"},
        "admission_proof": {"name": "Test User"},
    }
    monkeypatch.setattr("app.main.extract_document",
                        lambda path, doc_type: {"fields": fake[doc_type], "ocr_conf": 90.0, "error": None})

    tok = c.post("/auth/register", json={"email": "ok@x.com", "password": "pw12345"}).json()["token"]
    sid = c.get("/schemes").json()[0]["id"]
    aid = c.post("/applications", headers=H(tok), json={"scheme_id": sid}).json()["id"]
    c.put(f"/applications/{aid}", headers=H(tok),
          json={"category": "ST", "family_income": 300000, "enrolled_in_phd": True, "pg_percentage": 72})
    for d in fake:
        c.post(f"/applications/{aid}/documents?doc_type={d}", headers=H(tok),
               files={"file": (f"{d}.pdf", io.BytesIO(b"x"))})
    r = c.post(f"/applications/{aid}/submit", headers=H(tok)).json()
    assert r["eligibility"]["result"] == "ELIGIBLE"


def test_mismatch_downgrades_to_needs_review(monkeypatch):
    fake = {
        "caste_certificate": {"category": "ST"},
        "income_certificate": {"family_income": "300000"},
        "marksheet": {"pg_percentage": "55"},   # form says 72 -> mismatch
        "admission_proof": {},
    }
    monkeypatch.setattr("app.main.extract_document",
                        lambda path, doc_type: {"fields": fake[doc_type], "ocr_conf": 90.0, "error": None})

    tok = c.post("/auth/register", json={"email": "mm@x.com", "password": "pw12345"}).json()["token"]
    sid = c.get("/schemes").json()[0]["id"]
    aid = c.post("/applications", headers=H(tok), json={"scheme_id": sid}).json()["id"]
    c.put(f"/applications/{aid}", headers=H(tok),
          json={"category": "ST", "family_income": 300000, "enrolled_in_phd": True, "pg_percentage": 72})
    for d in fake:
        c.post(f"/applications/{aid}/documents?doc_type={d}", headers=H(tok),
               files={"file": (f"{d}.pdf", io.BytesIO(b"x"))})
    r = c.post(f"/applications/{aid}/submit", headers=H(tok)).json()
    assert r["eligibility"]["result"] == "NEEDS_REVIEW"
    assert any(x["rule"] == "AI document cross-check" for x in r["eligibility"]["reasons"])    