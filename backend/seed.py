"""Run once: python seed.py  -> creates NFST scheme + demo users."""
from app.db import SessionLocal, Base, engine
from app.models import User, Scheme
from app.security import hash_password

NFST = {
    "form_fields": [
        {"name": "category", "label": "Category", "type": "select", "options": ["ST", "SC", "OBC", "GEN"]},
        {"name": "family_income", "label": "Annual family income (INR)", "type": "number"},
        {"name": "enrolled_in_phd", "label": "Enrolled in M.Phil/Ph.D.", "type": "boolean"},
        {"name": "pg_percentage", "label": "Post-graduation %", "type": "number"},
    ],
    "required_documents": ["caste_certificate", "income_certificate", "admission_proof", "marksheet"],
    "eligibility_rules": [
        {"label": "Must be ST", "field": "category", "operator": "equals", "value": "ST"},
        # PLACEHOLDER: take the real limit from the official scheme guidelines
        {"label": "Income within limit", "field": "family_income", "operator": "lte", "value": 600000},
        {"label": "Enrolled in research programme", "field": "enrolled_in_phd", "operator": "equals", "value": True},
    ],
    "scoring": {"pg_percentage": 1.0},
    "selection": {"slots": 3, "waitlist": 2},
}


def run():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    if not db.query(Scheme).filter_by(code="NFST").first():
        db.add(Scheme(code="NFST", name="National Fellowship for Scheduled Tribe", config=NFST))
    for email, role in [("admin@mota.test", "admin"), ("officer@mota.test", "officer"),
                        ("approver@mota.test", "approver")]:
        if not db.query(User).filter_by(email=email).first():
            db.add(User(email=email, full_name=role.title(), role=role,
                        password_hash=hash_password("password123")))
    db.commit()
    print("Seeded.")


if __name__ == "__main__":
    run()