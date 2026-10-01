from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path("sample_docs"); OUT.mkdir(exist_ok=True)

def font(size):
    for f in ("DejaVuSans.ttf", "arial.ttf"):
        try: return ImageFont.truetype(f, size)
        except OSError: pass
    return ImageFont.load_default()

def make(name, title, lines):
    img = Image.new("RGB", (1200, 800), "white"); d = ImageDraw.Draw(img)
    d.text((60, 40), title, fill="black", font=font(40))
    for i, ln in enumerate(lines):
        d.text((60, 160 + i * 70), ln, fill="black", font=font(32))
    img.save(OUT / name)

NAME = "Asha Kumari Meena"
make("caste_ok.png", "SCHEDULED TRIBE CERTIFICATE (SAMPLE)", [
    "Certificate No: ST/UP/2024/00123", f"Name: {NAME}",
    "The applicant belongs to the Meena Scheduled Tribe."])
make("marksheet_ok.png", "UNIVERSITY MARKSHEET (SAMPLE)", [
    f"Name of Student: {NAME}", "Programme: M.Sc. Physics", "Percentage: 72.5"])
make("marksheet_bad.png", "UNIVERSITY MARKSHEET (SAMPLE)", [
    f"Name of Student: {NAME}", "Programme: M.Sc. Physics", "Percentage: 55.0"])
make("income_ok.png", "INCOME CERTIFICATE (SAMPLE)", [
    f"Name: {NAME}", "Annual Income: Rs 250000"])
make("admission_ok.png", "PH.D. ADMISSION LETTER (SAMPLE)", [
    f"Name of Student: {NAME}", "Programme: Ph.D. Physics", "Session: 2026-27"])    
print("Created in ./sample_docs")