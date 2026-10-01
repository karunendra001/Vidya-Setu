"""OCR + cross-check. Assistive only: it can raise a flag, never reject."""
import os, re
from pathlib import Path
from PIL import Image, ImageOps
import pytesseract
from rapidfuzz import fuzz

if os.getenv("TESSERACT_CMD"):  # e.g. C:\Program Files\Tesseract-OCR\tesseract.exe
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]

# ====== MATCHED TO seed.py (NFST) ============================================
EXTRACTORS = {
    "caste_certificate": {
        "name": r"name(?: of (?:the )?(?:applicant|student))?\s*[:\-]\s*([A-Za-z .]+)",
        "category": r"belongs to .{0,40}?(scheduled tribe|scheduled caste)",
        "certificate_no": r"certificate\s*(?:no|number)\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
    },
    "income_certificate": {
        "name": r"name\s*[:\-]\s*([A-Za-z .]+)",
        "family_income": r"annual income[^0-9]{0,30}([\d,]+)",
    },
    "marksheet": {
        "name": r"name of (?:the )?student\s*[:\-]\s*([A-Za-z .]+)",
        "pg_percentage": r"(?:percentage|cgpa)\s*[:\-]?\s*(\d+(?:\.\d+)?)",
    },
    "admission_proof": {
        "name": r"name of (?:the )?(?:student|scholar)\s*[:\-]\s*([A-Za-z .]+)",
    },
}
# extracted field -> form_data key. "name" falls back to the applicant's registered full name.
FORM_KEY = {
    "name": "full_name",
    "category": "category",
    "family_income": "family_income",
    "pg_percentage": "pg_percentage",
    "certificate_no": None,
}
# Normalise document wording to the form's option values
ALIASES = {"scheduled tribe": "ST", "scheduled caste": "SC"}
# =============================================================================

NUMERIC = {"family_income", "pg_percentage"}


def _ocr_image(img):
    img = ImageOps.autocontrast(ImageOps.grayscale(img))
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    confs = [float(c) for t, c in zip(data["text"], data["conf"]) if t.strip() and float(c) >= 0]
    return pytesseract.image_to_string(img), (sum(confs) / len(confs) if confs else 0.0)


def _read(path):
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        from pdf2image import convert_from_path
        pages = convert_from_path(str(p), dpi=200, first_page=1, last_page=2)
        res = [_ocr_image(pg) for pg in pages]
        return "\n".join(t for t, _ in res), sum(c for _, c in res) / len(res)
    return _ocr_image(Image.open(p))


def extract_document(path, doc_type):
    """Called at upload. Returns a JSON-safe dict stored in Document.ocr_data.
    Never raises: OCR trouble must not block an upload."""
    try:
        text, conf = _read(path)
        fields = {}
        for field, rx in EXTRACTORS.get(doc_type, {}).items():
            m = re.search(rx, text, re.I)
            v = m.group(1).strip() if m else None
            fields[field] = ALIASES.get(v.lower(), v) if v else None
        return {"fields": fields, "ocr_conf": round(conf, 1), "error": None}
    except Exception as e:
        return {"fields": {}, "ocr_conf": 0.0, "error": str(e)[:150]}


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", str(s).lower()).strip()


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def compare_field(field, form_value, extracted):
    """-> (status, score). status: match | review | mismatch | not_found | info"""
    if extracted in (None, ""):
        return "not_found", 0.0
    if form_value in (None, ""):
        return "info", 0.0
    if field in NUMERIC:
        a, b = _num(form_value), _num(extracted)
        if a is None or b is None:
            return "review", 0.0
        diff = abs(a - b) / max(abs(a), 1e-9)
        return ("match", 100.0) if diff <= 0.01 else ("review", 60.0) if diff <= 0.05 else ("mismatch", 0.0)
    score = fuzz.token_sort_ratio(_norm(form_value), _norm(extracted))
    return ("match" if score >= 85 else "review" if score >= 60 else "mismatch"), float(score)


def compare_documents(docs, form_data, applicant_name=""):
    """docs: list of (doc_type, ocr_data). Returns a list of check rows."""
    rows = []
    for doc_type, ocr in docs:
        ocr = ocr or {}
        if ocr.get("error"):
            rows.append({"doc_type": doc_type, "field": "ocr_error", "form_value": "",
                         "extracted_value": ocr["error"], "status": "review", "score": 0.0})
            continue
        if not ocr.get("fields"):
            continue  # doc type has no extractor, or OCR not run
        for field, extracted in ocr["fields"].items():
            key = FORM_KEY.get(field)
            fv = form_data.get(key) if key else None
            if field == "name" and fv in (None, ""):
                fv = applicant_name
            status, score = compare_field(field, fv, extracted)
            rows.append({"doc_type": doc_type, "field": field, "form_value": "" if fv is None else str(fv),
                         "extracted_value": extracted or "", "status": status, "score": score})
        if ocr.get("ocr_conf", 100) < 50:
            rows.append({"doc_type": doc_type, "field": "scan_quality", "form_value": "",
                         "extracted_value": f"{ocr['ocr_conf']:.0f}% confidence",
                         "status": "review", "score": ocr["ocr_conf"]})
    return rows


def overall_status(rows):
    if any(r["status"] == "mismatch" for r in rows):
        return "mismatch"
    if any(r["status"] in ("review", "not_found") for r in rows):
        return "review"
    return "ok" if rows else "pending"