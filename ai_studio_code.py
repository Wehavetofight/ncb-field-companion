import streamlit as st
import cv2
import numpy as np
import json
import hashlib
import tempfile
from datetime import datetime
import pytz
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import pyttsx3
 ---------------- PAGE ----------------
st.set_page_config(page_title="NCB Field Companion",
                   page_icon="🛡️",
                   layout="wide")

st.title("🛡️ NCB FIELD COMPANION")
st.caption("AI Presumptive Drug Identification Tool")

# Prevent repeated speech
if "spoken" not in st.session_state:
    st.session_state.spoken = False

# Load reagent database
with open("reagents.json", "r") as f:
    reagents = json.load(f)

# Text-to-Speech
def talk_back(text):
    if st.session_state.spoken:
        return
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
    st.session_state.spoken = True

# RGB → LAB
def rgb_to_lab(rgb):
    rgb = np.uint8([[rgb]])
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    return lab[0][0]

# Color distance
def color_distance(l1, l2):
    return np.linalg.norm(np.array(l1) - np.array(l2))

# PDF Generator
def generate_pdf(officer, case, drug, confidence, rgb, lab, image):
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz).strftime("%d-%m-%Y %H:%M:%S")

    report_hash = hashlib.sha256(
        f"{officer}{case}{drug}{now}".encode()
    ).hexdigest()

    pdf_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    doc = SimpleDocTemplate(pdf_path)
    styles = getSampleStyleSheet()

    story = []
    story.append(Paragraph("<b>NCB FIELD COMPANION REPORT</b>", styles["Title"]))
    story.append(Paragraph(f"Officer ID: {officer}", styles["BodyText"]))
    story.append(Paragraph(f"Case Ref: {case}", styles["BodyText"]))
    story.append(Paragraph(f"Time (IST): {now}", styles["BodyText"]))
    story.append(Paragraph(f"Suspected Drug: <b>{drug}</b>", styles["BodyText"]))
    story.append(Paragraph(f"Confidence: {confidence:.1f}%", styles["BodyText"]))
    story.append(Paragraph(f"RGB: {rgb}", styles["BodyText"]))
    story.append(Paragraph(f"LAB: {lab}", styles["BodyText"]))
    story.append(Paragraph(f"SHA256 Hash: {report_hash}", styles["BodyText"]))

    img_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    cv2.imwrite(img_path, cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    story.append(Image(img_path, width=3*inch, height=3*inch))

    doc.build(story)

    with open(pdf_path, "rb") as f:
        return f.read()
        # ---------------- SIDEBAR ----------------
st.sidebar.header("Officer Details")
officer_id = st.sidebar.text_input("Officer ID")
case_ref = st.sidebar.text_input("Case Reference")

brightness = st.sidebar.slider("Brightness", -50, 50, 0)

# ---------------- CAMERA ----------------
photo = st.camera_input("Capture Reagent Test")

if photo is not None:

    # Reset speech for new image
    st.session_state.spoken = False

    file_bytes = np.asarray(bytearray(photo.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Brightness adjustment
    img = np.clip(img.astype(np.int16) + brightness, 0, 255).astype(np.uint8)

    h, w, _ = img.shape

    # Center ROI
    roi = img[h//2-20:h//2+20, w//2-20:w//2+20]
    avg_rgb = roi.mean(axis=(0,1)).astype(int).tolist()
    avg_lab = rgb_to_lab(avg_rgb)

    st.image(img, caption="Captured Image", use_container_width=True)
    st.success(f"Detected RGB: {avg_rgb}")
    st.info(f"LAB Value: {avg_lab.tolist()}")

    # ---------------- AI MATCH ----------------
    best_match = None
    best_distance = 9999

    for item in reagents:
        reagent_lab = item["lab"]
        dist = color_distance(avg_lab, reagent_lab)

        if dist < best_distance:
            best_distance = dist
            best_match = item

    confidence = max(0, min(100, 100 - best_distance * 2))

    # ---------------- RESULT ----------------
    if confidence >= 70:
        drug = best_match["drug"]
        st.success(f"🧪 Suspected Drug: {drug}")
        st.metric("Confidence", f"{confidence:.1f}%")
        talk_back(f"Possible match detected. {drug}")
    else:
        drug = "Inconclusive — Laboratory confirmation required"
        st.warning(drug)
        st.metric("Confidence", f"{confidence:.1f}%")
        talk_back("Result is inconclusive. Laboratory confirmation required.")

    # ---------------- PDF DOWNLOAD ----------------
    if st.button("📄 Generate PDF Report"):
        pdf = generate_pdf(
            officer_id,
            case_ref,
            drug,
            confidence,
            avg_rgb,
            avg_lab.tolist(),
            img
        )

        st.download_button(
            label="⬇️ Download NCB Report",
            data=pdf,
            file_name=f"NCB_Report_{case_ref or 'CASE'}.pdf",
            mime="application/pdf"
        )
