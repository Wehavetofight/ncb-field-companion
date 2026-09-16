"""Repaired Python prototype. Run: streamlit run ai_studio_code.py

Dependencies: streamlit, numpy, Pillow, reportlab.
Keep the original reagents.json next to this file.
This is a single-image demo, not a port of the Android evidence workflow.
"""
import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as PDFImage


def rgb_to_lab(rgb):
    """sRGB -> linear RGB -> D65 XYZ -> CIELAB (not OpenCV byte Lab)."""
    rgb = np.asarray(rgb, dtype=float) / 255.0
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = np.array([[.4124564, .3575761, .1804375],
                    [.2126729, .7151522, .0721750],
                    [.0193339, .1191920, .9503041]]) @ linear
    xyz /= np.array([.95047, 1., 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def load_database(path):
    db = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(db, dict) or not db:
        raise ValueError("Expected a non-empty JSON object of reagent reference entries.")
    for key, entry in db.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid entry: {key}")
        for field in ("reagent", "target_compound"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"Missing {field} in {key}")
        lab = np.asarray(entry.get("target_lab"), dtype=float)
        tol = float(entry.get("tolerance_de", 22))
        if lab.shape != (3,) or not np.isfinite(lab).all() or not np.isfinite(tol) or tol <= 0:
            raise ValueError(f"Invalid Lab/tolerance in {key}")
    return db


def classify(lab, db, reagent):
    if any(name in reagent.lower() for name in ("scott", "duquenois")):
        return "INCONCLUSIVE", "This multi-stage/layered test requires manual protocol review.", None
    candidates = sorted(
        [(float(np.linalg.norm(lab - np.asarray(e["target_lab"]))), key, e)
         for key, e in db.items() if e["reagent"] == reagent], key=lambda item: item[0])
    if not candidates:
        return "INCONCLUSIVE", "No reference for the selected reagent.", None
    distance, _, best = candidates[0]
    if distance > float(best.get("tolerance_de", 22)):
        return "INCONCLUSIVE", "Outside the demonstration reference tolerance. This is not a negative result.", distance
    if len(candidates) > 1 and candidates[1][0] - distance < 5:
        return "INCONCLUSIVE", "Ambiguous reference match.", distance
    return "DEMO COLOUR MATCH", f"Colour resembles the unvalidated reference labelled {best['target_compound']}. Substance identity is not established.", distance


def generate_pdf(record, photo):
    out = BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph("FIELD COMPANION - STUDENT PROTOTYPE", styles["Title"]), Spacer(1, 14)]
    for key, value in record.items():
        text = json.dumps(value, ensure_ascii=True) if isinstance(value, (list, dict)) else str(value)
        story.append(Paragraph(f"<b>{escape(key)}:</b> {escape(text)}", styles["BodyText"]))
        story.append(Spacer(1, 8))
    preview = ImageOps.exif_transpose(Image.open(BytesIO(photo))).convert("RGB")
    preview.thumbnail((900, 900))
    buf = BytesIO()
    preview.save(buf, format="PNG")
    buf.seek(0)
    scale = min(450 / preview.width, 320 / preview.height)
    story.append(PDFImage(buf, width=preview.width * scale, height=preview.height * scale))
    story.append(Paragraph("Presumptive screening demonstration only. Laboratory confirmation is required. An image hash is not a digital signature or proof of capture authenticity.", styles["BodyText"]))
    SimpleDocTemplate(out).build(story)
    return out.getvalue()


def main():
    st.set_page_config(page_title="NCB Field Companion", page_icon="📷", layout="wide")
    st.title("NCB Field Companion")
    st.caption("Independent student prototype - not an official NCB application")
    st.warning("Presumptive demonstration only. Reference colours are unvalidated; laboratory confirmation is required.")
    st.info("Python repair: single-photo colour comparison and PDF export. GPS, reference-card correction, reaction-sequence checks, signed records and a persistent log are not implemented in this version.")
    try:
        db = load_database(Path(__file__).resolve().with_name("reagents.json"))
    except (OSError, ValueError, TypeError) as exc:
        st.error(f"Cannot load reagents.json: {exc}")
        st.stop()
    officer = st.sidebar.text_input("Officer / operator ID")
    case = st.sidebar.text_input("Case reference")
    reagent = st.sidebar.selectbox("Reagent used", sorted({e["reagent"] for e in db.values()}))
    photo = st.camera_input("Place the reaction in the centre; capture with even lighting")
    if photo is None:
        return
    raw = photo.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    if st.session_state.get("photo_digest") != digest:
        st.session_state.photo_digest = digest
        st.session_state.received_at = datetime.now(timezone.utc).isoformat()
    try:
        pic = ImageOps.exif_transpose(Image.open(BytesIO(raw))).convert("RGB")
        if min(pic.size) < 30:
            raise ValueError("Image too small for a 30-pixel sample region.")
        pic.thumbnail((1600, 1600))
        pixels = np.asarray(pic)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        st.error(f"Cannot analyse this image: {exc}")
        return
    h, w = pixels.shape[:2]
    roi = pixels[h // 2 - 15:h // 2 + 15, w // 2 - 15:w // 2 + 15]
    rgb = roi.mean(axis=(0, 1))
    lab = rgb_to_lab(rgb)
    outcome, detail, distance = classify(lab, db, reagent)
    st.image(pic, caption="Captured image", use_container_width=True)
    st.image(roi, caption="Centre 30 x 30 pixel analysis region", width=180)
    st.write("Mean RGB:", rgb.round(1).tolist(), "CIELAB:", lab.round(2).tolist())
    st.subheader(outcome)
    st.write(detail)
    if distance is not None:
        st.write(f"Nearest reference ΔE76: {distance:.2f} (not a confidence percentage)")
    st.caption("A static shirt or other similarly coloured object can match this single-photo demo. It does not authenticate a chemical reaction.")
    record = {
        "operator_id": officer.strip(), "case_reference": case.strip(), "reagent": reagent,
        "image_received_at_utc": st.session_state.received_at,
        "timestamp_source": "Server receipt time; not verified camera exposure time",
        "rgb": rgb.round(3).tolist(), "lab_d65": lab.round(3).tolist(),
        "roi_analysis_pixels": [w // 2 - 15, h // 2 - 15, w // 2 + 15, h // 2 + 15],
        "analysis_image_size": [w, h], "outcome": outcome, "detail": detail,
        "delta_e76": distance, "original_image_sha256": digest,
        "location": "Not collected", "signature": "Not implemented",
    }
    st.code(digest, language=None)
    if not officer.strip() or not case.strip():
        st.info("Enter operator ID and case reference to enable report export.")
        return
    st.download_button("Download PDF report", generate_pdf(record, raw),
                       file_name=f"FieldCompanion_{digest[:12]}.pdf", mime="application/pdf")
    st.download_button("Download JSON record", json.dumps(record, indent=2),
                       file_name=f"FieldCompanion_{digest[:12]}.json", mime="application/json")
    st.download_button("Download original image", raw, file_name=f"original_{digest[:12]}{Path(photo.name).suffix}",
                       mime=photo.type or "application/octet-stream")


if __name__ == "__main__":
    main()
