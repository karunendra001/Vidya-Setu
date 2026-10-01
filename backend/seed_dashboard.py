"""python seed_dashboard.py        -> adds ~400 DUMMY applications for the Ministry dashboard
   python seed_dashboard.py clear  -> removes them again"""
import json, random, sys
from datetime import datetime, timedelta
from app.db import SessionLocal, Base, engine
from app.models import User, Scheme, Application, AuditLog
from app.security import hash_password

random.seed(26239)
SUFFIX = "@example.test"
STATES = [("Madhya Pradesh", 16), ("Chhattisgarh", 12), ("Jharkhand", 11), ("Odisha", 11),
          ("Gujarat", 8), ("Rajasthan", 8), ("Maharashtra", 8), ("Assam", 6),
          ("Telangana", 5), ("Andhra Pradesh", 5), ("Meghalaya", 5), ("Tripura", 3), ("Uttar Pradesh", 2)]
GENDERS = [("Female", 47), ("Male", 52), ("Other", 1)]
DEFICIENCY = ["Caste certificate name does not match application",
              "Income certificate unreadable, please re-upload",
              "Marksheet percentage differs from the form",
              "Admission proof does not show the session",
              "Income certificate is older than one year"]


def pick(pairs):
    return random.choices([p[0] for p in pairs], weights=[p[1] for p in pairs])[0]


def reject_reason(fd):
    if fd["category"] != "ST":
        return "Not a Scheduled Tribe applicant"
    if fd["family_income"] > 600000:
        return "Family income above the limit"
    return "Not enrolled in a research programme"


def review_time(t):
    return t + timedelta(days=min(30, random.lognormvariate(1.2, 0.6)))


def history(uid, fd, elig, officers, now):
    """Returns (status, note, audit events)."""
    if random.random() < 0.07:
        return "DRAFT", "", []
    t0 = now - timedelta(days=random.uniform(0.5, 150))
    ev = [("SUBMIT", uid, t0, {"eligibility": elig["result"]})]
    t1 = review_time(t0)
    if t1 > now:
        return "SUBMITTED", "", ev
    off = random.choice(officers).id
    if elig["result"] == "NOT_ELIGIBLE":
        note = reject_reason(fd)
        ev.append(("DECISION", off, t1, {"decision": "REJECTED", "note": note}))
        return "REJECTED", note, ev
    if random.random() < 0.22:
        note = random.choice(DEFICIENCY)
        ev.append(("DECISION", off, t1, {"decision": "DEFICIENT", "note": note}))
        t2 = t1 + timedelta(days=random.uniform(1, 8))
        if random.random() < 0.3 or t2 > now:
            return "DEFICIENT", note, ev
        ev.append(("SUBMIT", uid, t2, {"eligibility": elig["result"]}))
        t3 = review_time(t2)
        if t3 > now:
            return "SUBMITTED", "", ev
        ev.append(("DECISION", off, t3, {"decision": "VERIFIED", "note": ""}))
        return "VERIFIED", "", ev
    ev.append(("DECISION", off, t1, {"decision": "VERIFIED", "note": ""}))
    return "VERIFIED", "", ev


def run():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    nfst = db.query(Scheme).filter_by(code="NFST").first()
    if not nfst:
        print("Run seed.py first"); return
    if db.query(User).filter(User.email.like("sim%" + SUFFIX)).first():
        print("Dummy data already present. Run: python seed_dashboard.py clear"); return
    nos = db.query(Scheme).filter_by(code="NOS").first()
    if not nos:
        cfg = json.loads(json.dumps(nfst.config))
        cfg["selection"] = {"slots": 40, "waitlist": 20}
        nos = Scheme(code="NOS", name="National Overseas Scholarship (demo config)", config=cfg)
        db.add(nos); db.flush()

    pw = hash_password("password123")           # hash once: bcrypt is slow
    officers = [User(email=f"simoff{k}{SUFFIX}", full_name=f"Officer {chr(64 + k)} (demo)",
                     role="officer", password_hash=pw) for k in (1, 2, 3)]
    db.add_all(officers); db.flush()

    now = datetime.utcnow()
    for scheme, n in ((nfst, 260), (nos, 140)):
        batch = []
        for i in range(n):
            u = User(email=f"sim{scheme.code.lower()}{i + 1}{SUFFIX}",
                     full_name=f"Dummy {scheme.code} {i + 1}", role="applicant", password_hash=pw)
            db.add(u); db.flush()
            fd = {"category": "ST" if random.random() < 0.93 else random.choice(["SC", "OBC", "GEN"]),
                  "family_income": random.randint(80, 900) * 1000,
                  "enrolled_in_phd": random.random() < 0.92,
                  "pg_percentage": round(random.uniform(50, 95), 1),
                  "state": pick(STATES), "gender": pick(GENDERS)}
            if fd["category"] != "ST" or fd["family_income"] > 600000 or not fd["enrolled_in_phd"]:
                elig = {"result": "NOT_ELIGIBLE", "reasons": []}
            else:
                elig = {"result": "NEEDS_REVIEW" if random.random() < 0.15 else "ELIGIBLE", "reasons": []}
            status, note, ev = history(u.id, fd, elig, officers, now)
            a = Application(user_id=u.id, scheme_id=scheme.id, form_data=fd, status=status,
                            eligibility=elig if status != "DRAFT" else {}, officer_note=note,
                            created_at=(ev[0][2] - timedelta(days=1)) if ev else now)
            db.add(a); db.flush()
            for action, actor, at, detail in ev:
                db.add(AuditLog(actor_id=actor, action=action, entity="application",
                                entity_id=a.id, detail=detail, at=at))
            batch.append(a)
        if scheme.code == "NOS":                # simulate a published result for this scheme
            ver = sorted([a for a in batch if a.status == "VERIFIED"],
                         key=lambda a: -a.form_data["pg_percentage"])
            for pos, a in enumerate(ver, 1):
                a.status = "SELECTED" if pos <= 40 else "WAITLISTED" if pos <= 60 else "NOT_SELECTED"
                a.officer_note = f"Result: {a.status.replace('_', ' ')} (merit rank {pos} of {len(ver)})."
    db.commit()
    print("Added dummy applications. All accounts: sim*@example.test / password123")


def clear():
    db = SessionLocal()
    users = db.query(User).filter(User.email.like("sim%" + SUFFIX)).all()
    uids = [u.id for u in users]
    apps = db.query(Application).filter(Application.user_id.in_(uids)).all() if uids else []
    aids = [a.id for a in apps]
    if aids:
        db.query(AuditLog).filter(AuditLog.entity == "application",
                                  AuditLog.entity_id.in_(aids)).delete(synchronize_session=False)
    for a in apps:
        db.delete(a)
    db.flush()
    for u in users:
        db.delete(u)
    nos = db.query(Scheme).filter_by(code="NOS").first()
    if nos and not db.query(Application).filter_by(scheme_id=nos.id).first():
        db.delete(nos)
    db.commit()
    print("Dummy data removed.")


if __name__ == "__main__":
    clear() if len(sys.argv) > 1 and sys.argv[1] == "clear" else run()