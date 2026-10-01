import os, re, shutil, uuid
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from .db import Base, engine, get_db
from .models import User, Scheme, Application, Document, AuditLog, RankOverride
from .security import hash_password, verify_password, make_token, current_user, require_roles
from .rules import evaluate, missing_documents
from .ocr_service import extract_document, compare_documents, overall_status
from .ranking import score_application, build_ranking
from .analytics import compute_dashboard

Base.metadata.create_all(engine)
# Private folder: never mounted as static files. Served only via /documents/{id}/download.
UPLOAD_DIR = os.path.abspath("uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
STAFF = ("officer", "approver", "admin")
COMMITTEE = ("approver", "admin")
FINAL = ("SELECTED", "WAITLISTED", "NOT_SELECTED")

app = FastAPI(title="Vidya Setu: MoTA Scholarship & Fellowship Management System")

# React dev server (Vite) by default; override with CORS_ORIGINS="https://a.gov.in,https://b.gov.in"
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


def audit(db, actor, action, entity, entity_id, detail=None):
    db.add(AuditLog(actor_id=actor.id, action=action, entity=entity,
                    entity_id=entity_id, detail=detail or {}))


# ---------- Auth ----------
class RegisterIn(BaseModel):
    email: str
    password: str
    full_name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(400, "Email already registered")
    u = User(email=body.email, full_name=body.full_name,
             password_hash=hash_password(body.password), role="applicant")
    db.add(u); db.commit()
    return {"token": make_token(u), "role": u.role, "full_name": u.full_name}


@app.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(u), "role": u.role, "full_name": u.full_name}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


# ---------- Schemes ----------
@app.get("/schemes")
def list_schemes(db: Session = Depends(get_db)):
    return [{"id": s.id, "code": s.code, "name": s.name}
            for s in db.scalars(select(Scheme).where(Scheme.is_active))]


@app.get("/schemes/{scheme_id}")
def get_scheme(scheme_id: int, db: Session = Depends(get_db)):
    s = db.get(Scheme, scheme_id)
    if not s:
        raise HTTPException(404, "Scheme not found")
    return {"id": s.id, "code": s.code, "name": s.name, "config": s.config}


class SchemeIn(BaseModel):
    code: str
    name: str
    config: dict


@app.post("/admin/schemes")
def create_scheme(body: SchemeIn, db: Session = Depends(get_db),
                  admin: User = Depends(require_roles("admin"))):
    s = Scheme(code=body.code, name=body.name, config=body.config)
    db.add(s); db.flush()
    audit(db, admin, "CREATE_SCHEME", "scheme", s.id)
    db.commit()
    return {"id": s.id}


# ---------- Applicant ----------
class AppIn(BaseModel):
    scheme_id: int
    form_data: dict = {}


@app.post("/applications")
def create_application(body: AppIn, db: Session = Depends(get_db),
                       user: User = Depends(require_roles("applicant"))):
    if not db.get(Scheme, body.scheme_id):
        raise HTTPException(404, "Scheme not found")
    a = Application(user_id=user.id, scheme_id=body.scheme_id, form_data=body.form_data)
    db.add(a); db.commit()
    return {"id": a.id, "status": a.status}


def _own_app(db, app_id, user) -> Application:
    a = db.get(Application, app_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Application not found")
    return a


@app.put("/applications/{app_id}")
def save_draft(app_id: int, body: dict, db: Session = Depends(get_db),
               user: User = Depends(require_roles("applicant"))):
    a = _own_app(db, app_id, user)
    if a.status not in ("DRAFT", "DEFICIENT"):
        raise HTTPException(400, "Application can no longer be edited")
    a.form_data = {**a.form_data, **body}
    db.commit()
    return {"id": a.id, "form_data": a.form_data}


def _doc_out(d: Document) -> dict:
    return {"id": d.id, "doc_type": d.doc_type, "filename": d.filename,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "ocr_data": d.ocr_data}


def _app_out(db: Session, a: Application) -> dict:
    scheme = db.get(Scheme, a.scheme_id)
    docs = db.scalars(select(Document).where(Document.application_id == a.id)
                      .order_by(Document.id)).all()
    required = scheme.config.get("required_documents", []) if scheme else []
    return {
        "id": a.id,
        "scheme": {"id": scheme.id, "code": scheme.code, "name": scheme.name} if scheme else None,
        "status": a.status,
        "form_data": a.form_data,
        "eligibility": a.eligibility,
        "officer_note": a.officer_note,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "documents": [_doc_out(d) for d in docs],
        "missing_documents": missing_documents(required, [d.doc_type for d in docs]),
        "editable": a.status in ("DRAFT", "DEFICIENT"),
    }


def _can_view(a: Application, user: User) -> bool:
    return a.user_id == user.id or user.role in STAFF

def _doc_checks(db: Session, a: Application) -> list:
    docs = db.scalars(select(Document).where(Document.application_id == a.id)).all()
    applicant = db.get(User, a.user_id)
    return compare_documents([(d.doc_type, d.ocr_data) for d in docs],
                             a.form_data or {}, applicant.full_name if applicant else "")    


@app.post("/applications/{app_id}/documents")
def upload_document(app_id: int, doc_type: str, file: UploadFile = File(...),
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles("applicant"))):
    a = _own_app(db, app_id, user)
    if a.status not in ("DRAFT", "DEFICIENT"):
        raise HTTPException(400, "Application can no longer be edited")
    scheme = db.get(Scheme, a.scheme_id)
    allowed_types = {d if isinstance(d, str) else d.get("type") or d.get("code")
                     for d in scheme.config.get("required_documents", [])}
    if allowed_types and doc_type not in allowed_types:
        raise HTTPException(400, f"Unknown document type '{doc_type}' for this scheme")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Only PDF, JPG or PNG files are allowed")

    # Server-generated name: user input never touches the filesystem path.
    stored = f"{a.id}_{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, stored)
    size = 0
    with open(path, "wb") as out:
        while chunk := file.file.read(1024 * 256):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close(); os.remove(path)
                raise HTTPException(413, "File too large (max 5 MB)")
            out.write(chunk)

    # Re-uploading the same document type replaces the old file.
    for old in db.scalars(select(Document).where(Document.application_id == a.id,
                                                 Document.doc_type == doc_type)):
        if os.path.exists(old.path):
            os.remove(old.path)
        db.delete(old)
    d = Document(application_id=a.id, doc_type=doc_type,
                 filename=os.path.basename(file.filename), path=path,
                 ocr_data=extract_document(path, doc_type))
    db.add(d); db.commit()
    return _doc_out(d)


@app.post("/applications/{app_id}/submit")
def submit(app_id: int, db: Session = Depends(get_db),
           user: User = Depends(require_roles("applicant"))):
    a = _own_app(db, app_id, user)
    if a.status not in ("DRAFT", "DEFICIENT"):
        raise HTTPException(400, "Already submitted")
    scheme = db.get(Scheme, a.scheme_id)
    cfg = scheme.config
    uploaded = [d.doc_type for d in db.scalars(select(Document).where(Document.application_id == a.id))]
    missing = missing_documents(cfg.get("required_documents", []), uploaded)
    if missing:
        raise HTTPException(400, {"message": "Missing documents", "missing": missing})
    empty = [f["label"] for f in cfg.get("form_fields", [])
             if a.form_data.get(f["name"]) in (None, "")]
    if empty:
        raise HTTPException(400, {"message": "Please fill all details", "missing": empty})

    a.eligibility = evaluate(cfg.get("eligibility_rules", []), a.form_data)
    checks = _doc_checks(db, a)
    doc_status = overall_status(checks)
    # OCR can only move ELIGIBLE -> NEEDS_REVIEW. It never produces NOT_ELIGIBLE.
    if doc_status in ("mismatch", "review"):
        a.eligibility = {
            **a.eligibility,
            "result": "NEEDS_REVIEW" if a.eligibility["result"] == "ELIGIBLE" else a.eligibility["result"],
            "reasons": a.eligibility["reasons"] + [{
                "rule": "AI document cross-check", "passed": None,
                "why": "Differences found between documents and form. Officer to verify."}],
        }
    a.status = "SUBMITTED"
    audit(db, user, "SUBMIT", "application", a.id, {"eligibility": a.eligibility["result"]})
    db.commit()
    return {"status": a.status, "eligibility": a.eligibility}
    

@app.get("/applications/mine")
def my_applications(db: Session = Depends(get_db),
                    user: User = Depends(require_roles("applicant"))):
    rows = db.scalars(select(Application).where(Application.user_id == user.id)
                      .order_by(Application.id.desc()))
    return [{"id": a.id, "scheme_id": a.scheme_id, "status": a.status,
             "officer_note": a.officer_note, "eligibility": a.eligibility} for a in rows]


# NOTE: declared after /applications/mine so "mine" isn't parsed as an id.
@app.get("/applications/{app_id}")
def get_application(app_id: int, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    a = db.get(Application, app_id)
    if not a or not _can_view(a, user):
        raise HTTPException(404, "Application not found")
    out = _app_out(db, a)
    if user.role in STAFF:
        applicant = db.get(User, a.user_id)
        out["applicant"] = {"id": applicant.id, "full_name": applicant.full_name,
                            "email": applicant.email}
        out["doc_checks"] = _doc_checks(db, a)
        out["doc_status"] = overall_status(out["doc_checks"])                    
    return out


@app.get("/documents/{doc_id}/download")
def download_document(doc_id: int, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    d = db.get(Document, doc_id)
    a = db.get(Application, d.application_id) if d else None
    if not d or not a or not _can_view(a, user):
        raise HTTPException(404, "Document not found")
    if not os.path.exists(d.path):
        raise HTTPException(410, "File is missing from storage")
    if user.role in STAFF:
        audit(db, user, "VIEW_DOCUMENT", "document", d.id, {"application_id": a.id})
        db.commit()
    return FileResponse(d.path, filename=d.filename,
                        content_disposition_type="inline")


# ---------- Officer ----------
@app.get("/officer/queue")
def queue(db: Session = Depends(get_db),
          officer: User = Depends(require_roles(*STAFF))):
    rows = db.scalars(select(Application).where(Application.status == "SUBMITTED"))
    out = []
    for a in rows:
        applicant = db.get(User, a.user_id)
        scheme = db.get(Scheme, a.scheme_id)
        out.append({"id": a.id, "scheme_id": a.scheme_id,
                    "scheme_name": scheme.name if scheme else None,
                    "applicant_name": applicant.full_name or applicant.email,
                    "form_data": a.form_data, "eligibility": a.eligibility})
    return out


class DecisionIn(BaseModel):
    decision: str          # VERIFIED | DEFICIENT | REJECTED
    note: str = ""


@app.post("/officer/applications/{app_id}/decision")
def decide(app_id: int, body: DecisionIn, db: Session = Depends(get_db),
           officer: User = Depends(require_roles(*STAFF))):
    if body.decision not in ("VERIFIED", "DEFICIENT", "REJECTED"):
        raise HTTPException(400, "Invalid decision")
    if body.decision != "VERIFIED" and not body.note:
        raise HTTPException(400, "A note is mandatory when not verifying")
    a = db.get(Application, app_id)
    if not a or a.status != "SUBMITTED":
        raise HTTPException(404, "No submitted application with that id")
    a.status, a.officer_note = body.decision, body.note
    audit(db, officer, "DECISION", "application", a.id, {"decision": body.decision, "note": body.note})
    db.commit()
    return {"id": a.id, "status": a.status}

@app.post("/officer/documents/{doc_id}/reverify")
def reverify(doc_id: int, db: Session = Depends(get_db),
             officer: User = Depends(require_roles(*STAFF))):
    d = db.get(Document, doc_id)
    if not d or not os.path.exists(d.path):
        raise HTTPException(404, "Document not found")
    d.ocr_data = extract_document(d.path, d.doc_type)
    audit(db, officer, "REVERIFY_DOCUMENT", "document", d.id)
    db.commit()
    return d.ocr_data    

# ---------- Selection committee ----------
def _ranking(db: Session, scheme: Scheme) -> dict:
    cfg = scheme.config or {}
    sel = cfg.get("selection", {})
    slots, waitlist = int(sel.get("slots", 0)), int(sel.get("waitlist", 0))
    apps = db.scalars(select(Application).where(
        Application.scheme_id == scheme.id,
        Application.status.in_(("VERIFIED",) + FINAL))).all()
    cands = []
    for a in apps:
        u = db.get(User, a.user_id)
        score, breakdown = score_application(cfg.get("scoring", {}), a.form_data or {})
        cands.append({"application_id": a.id, "name": (u.full_name or u.email) if u else "?",
                      "score": score, "breakdown": breakdown, "status": a.status,
                      "eligibility": (a.eligibility or {}).get("result")})
    ovr = {o.application_id: {"action": o.action, "rank": o.rank, "reason": o.reason}
           for o in db.scalars(select(RankOverride).where(RankOverride.scheme_id == scheme.id))}
    ranked, excluded = build_ranking(cands, ovr, slots, waitlist)
    return {"scheme": {"id": scheme.id, "name": scheme.name}, "slots": slots, "waitlist": waitlist,
            "published": any(c["status"] in FINAL for c in cands),
            "ranked": ranked, "excluded": excluded}


@app.get("/committee/schemes/{scheme_id}/ranking")
def get_ranking(scheme_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_roles(*STAFF))):
    scheme = db.get(Scheme, scheme_id)
    if not scheme:
        raise HTTPException(404, "Scheme not found")
    return _ranking(db, scheme)


class OverrideIn(BaseModel):
    application_id: int
    action: str                 # PIN | EXCLUDE | CLEAR
    rank: int | None = None
    reason: str = ""


@app.post("/committee/schemes/{scheme_id}/overrides")
def set_override(scheme_id: int, body: OverrideIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(*COMMITTEE))):
    scheme = db.get(Scheme, scheme_id)
    if not scheme:
        raise HTTPException(404, "Scheme not found")
    if _ranking(db, scheme)["published"]:
        raise HTTPException(400, "Results are already published")
    if body.action not in ("PIN", "EXCLUDE", "CLEAR"):
        raise HTTPException(400, "Action must be PIN, EXCLUDE or CLEAR")
    a = db.get(Application, body.application_id)
    if not a or a.scheme_id != scheme.id or a.status != "VERIFIED":
        raise HTTPException(404, "No verified application with that id in this scheme")
    existing = db.scalar(select(RankOverride).where(RankOverride.application_id == a.id))
    if body.action == "CLEAR":
        if existing:
            db.delete(existing)
    else:
        if not body.reason.strip():
            raise HTTPException(400, "A reason is mandatory for every override")
        if body.action == "PIN" and (body.rank is None or body.rank < 1):
            raise HTTPException(400, "Give the rank position to pin to (1 or more)")
        rank = body.rank if body.action == "PIN" else None
        if existing:
            existing.action, existing.rank = body.action, rank
            existing.reason, existing.set_by = body.reason.strip(), user.id
        else:
            db.add(RankOverride(scheme_id=scheme.id, application_id=a.id, action=body.action,
                                rank=rank, reason=body.reason.strip(), set_by=user.id))
    audit(db, user, "RANK_OVERRIDE", "application", a.id,
          {"action": body.action, "rank": body.rank, "reason": body.reason})
    db.commit()
    return _ranking(db, scheme)


@app.post("/committee/schemes/{scheme_id}/publish")
def publish_results(scheme_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(*COMMITTEE))):
    scheme = db.get(Scheme, scheme_id)
    if not scheme:
        raise HTTPException(404, "Scheme not found")
    r = _ranking(db, scheme)
    if r["published"]:
        raise HTTPException(400, "Results are already published")
    if not r["slots"]:
        raise HTTPException(400, "No slots configured for this scheme")
    if not r["ranked"]:
        raise HTTPException(400, "No verified applications to rank")
    n = len(r["ranked"])
    for row in r["ranked"]:
        a = db.get(Application, row["application_id"])
        a.status = row["decision"]
        a.officer_note = f"Result: {row['decision'].replace('_', ' ')} (merit rank {row['rank']} of {n})."
    for row in r["excluded"]:
        a = db.get(Application, row["application_id"])
        a.status = "NOT_SELECTED"
        a.officer_note = "Result: NOT SELECTED (removed by the selection committee)."
    audit(db, user, "PUBLISH_RESULTS", "scheme", scheme.id, {
        "slots": r["slots"], "waitlist": r["waitlist"],
        "snapshot": [{"application_id": x["application_id"], "rank": x["rank"], "score": x["score"],
                      "decision": x["decision"], "override": x["override"]} for x in r["ranked"]]
                    + [{"application_id": x["application_id"], "decision": "EXCLUDED",
                        "override": x["override"]} for x in r["excluded"]]})
    db.commit()
    return {"published": True,
            "selected": sum(1 for x in r["ranked"] if x["decision"] == "SELECTED"),
            "waitlisted": sum(1 for x in r["ranked"] if x["decision"] == "WAITLISTED")}

# ---------- Ministry dashboard ----------
@app.get("/ministry/dashboard")
def ministry_dashboard(db: Session = Depends(get_db),
                       user: User = Depends(require_roles(*COMMITTEE))):
    apps = [{"id": a.id, "scheme_id": a.scheme_id, "status": a.status,
             "form_data": a.form_data or {},
             "eligibility_result": (a.eligibility or {}).get("result"),
             "created_at": a.created_at} for a in db.scalars(select(Application))]
    events = [{"application_id": e.entity_id, "action": e.action, "actor_id": e.actor_id,
               "at": e.at, "detail": e.detail or {}}
              for e in db.scalars(select(AuditLog).where(
                  AuditLog.entity == "application",
                  AuditLog.action.in_(("SUBMIT", "DECISION"))))]
    schemes = {s.id: s.name for s in db.scalars(select(Scheme))}
    names = {u.id: (u.full_name or u.email)
             for u in db.scalars(select(User).where(User.role.in_(STAFF)))}
    out = compute_dashboard(apps, events, schemes, names)
    out["has_demo_data"] = bool(db.scalar(
        select(func.count()).select_from(User).where(User.email.like("%@example.test"))))
    return out
     