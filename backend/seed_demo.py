"""python seed_demo.py -> adds DUMMY verified NFST applicants for the ranking demo."""
from app.db import SessionLocal, Base, engine
from app.models import User, Scheme, Application
from app.security import hash_password

DEMO = [("Demo Applicant 1", 84.2), ("Demo Applicant 2", 78.5), ("Demo Applicant 3", 78.5),
        ("Demo Applicant 4", 91.0), ("Demo Applicant 5", 66.4), ("Demo Applicant 6", 72.0),
        ("Demo Applicant 7", 88.6), ("Demo Applicant 8", 59.9)]


def run():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    scheme = db.query(Scheme).filter_by(code="NFST").first()
    if not scheme:
        print("Run seed.py first"); return
    for i, (name, pct) in enumerate(DEMO, 1):
        email = f"demo{i}@example.test"
        if db.query(User).filter_by(email=email).first():
            continue
        u = User(email=email, full_name=name, role="applicant",
                 password_hash=hash_password("password123"))
        db.add(u); db.flush()
        db.add(Application(
            user_id=u.id, scheme_id=scheme.id, status="VERIFIED",
            form_data={"category": "ST", "family_income": 200000 + i * 20000,
                       "enrolled_in_phd": True, "pg_percentage": pct},
            eligibility={"result": "ELIGIBLE", "reasons": []}))
    db.commit()
    print("Demo applicants added (dummy data).")


if __name__ == "__main__":
    run()