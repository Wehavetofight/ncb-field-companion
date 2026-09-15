import streamlit as st
import cv2
import numpy as np
import hashlib
import json
import os
import pytz
import webcolors
from datetime import datetime
from io import BytesIO
from sklearn.linear_model import LogisticRegression
import streamlit.components.v1 as components

# PDF Forensic Libraries
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# ============================================================
# 1. CORE CONFIGURATION & TIME
# ============================================================
IST = pytz.timezone('Asia/Kolkata')
NCB_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Narcotics_Control_Bureau_logo.png/220px-Narcotics_Control_Bureau_logo.png"

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# ============================================================
# 2. VOICE ENGINE
# ============================================================
def talk_back(text):
    if text:
        components.html(f"""
            <script>
            window.speechSynthesis.cancel(); 
            var msg = new SpeechSynthesisUtterance("{text}");
            msg.lang = 'en-IN';
            msg.rate = 0.95;
            window.speechSynthesis.speak(msg);
            </script>
        """, height=0)

# ============================================================
# 3. AI MODEL (With Strong Neutral Class for Shirts/Walls)
# ============================================================
@st.cache_resource
def train_ncb_ai():
    # SIH Master Dataset
    db = {
        "Cocaine": {"lab": [38, 8, -48], "ndps": "Sec. 21 (Cocaine)"},
        "Heroin": {"lab": [24, 32, -18], "ndps": "Sec. 21 (Opiates)"},
        "Methamphetamine": {"lab": [48, 42, 45], "ndps": "Sec. 22 (Psychotropic)"},
        "Cannabis/THC": {"lab": [28, 22, -28], "ndps": "Sec. 20 (Cannabis)"},
        "LSD": {"lab": [45, 38, -12], "ndps": "Sec. 22 (Psychotropic)"}
    }
    
    X, y, labels, ndps_map = [], [], [], {}
    
    # CLASS 0: THE NEUTRAL DEFENSE (Prevents shirt/wall matches)
    # We train the AI on common background shades: White, Gray, Skin, and Fabric colors
    neutrals = [[70,0,0], [95,0,0], [20,0,0], [50,5,5], [40,10,-20], [85,2,10]] 
    for n_color in neutrals:
        for _ in range(250): # Heavy weighting for neutrals
            X.append(np.array(n_color) + np.random.normal(0, 2.5, 3))
            y.append(0)
    labels.append("Neutral / No Drug Detected")

    # Load Drug Classes
    for key, data in db.items():
        idx = len(labels)
        for _ in range(150):
            X.append(np.array(data['lab']) + np.random.normal(0, 2.0, 3))
            y.append(idx)
        ndps_map[idx] = data['ndps']
        labels.append(key)
        
    model = LogisticRegression(max_iter=2000)
    model.fit(np.array(X), np.array(y))
    return model, (labels, ndps_map)

# ============================================================
# 4. COLOR NAMING ENGINE (Forensic Palette)
# ============================================================
def get_universal_name(rgb):
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 15: return "Neutral Gray"

    forensic_colors = {
        "Crimson Red": (153, 0, 0), "Deep Maroon": (80, 0, 0), "Blood Orange": (255, 69, 0),
        "Golden Amber": (255, 191, 0), "Forest Green": (34, 139, 34), "Cobalt Blue": (0, 71, 171),
        "Midnight Blue": (25, 25, 112), "Deep Purple": (48, 25, 52), "Violet": (138, 43, 226)
    }
    best_name, min_dist = "Custom Shade", float('inf')
    for name, c_rgb in forensic_colors.items():
        dist = np.sqrt((c_rgb[0]-r)**2 + (c_rgb[1]-g)**2 + (c_rgb[2]-b)**2)
        if dist < min_dist: min_dist = dist; best_name = name
    return best_name

def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

# ============================================================
# 5. PDF GENERATOR
# ============================================================
def generate_forensic_report(case_info, color_data, result, conf, ndps, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        [Paragraph("<b>FIELD EVIDENCE RECORD</b>", styles['Normal']), ""],
        ["TIMESTAMP (IST)", case_info['time']], ["OFFICER ID", case_info['officer']],
        ["CASE REF", case_info['case']], ["------------------", "------------------"],
        ["DETECTED COLOR", color_data['name']], ["HEX / CIELAB", f"{color_data['hex']} / {color_data['lab']}"],
        ["AI PREDICTION", result], ["CONFIDENCE", f"{conf:.1f}%"], ["NDPS STATUTE", ndps],
        ["EVIDENCE HASH", img_hash],
    ]
    table = Table(data, colWidths=[160, 320])
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor("#002F6C")), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('PADDING', (0,0), (-1,-1), 10)]))
    doc.build([Paragraph("<b>NARCOTICS CONTROL BUREAU</b>", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# ============================================================
# 6. APP UI & LOGIC
# ============================================================
st.set_page_config(page_title="NCB AI Companion", page_icon="⚖️")

# Initialize speech variable to prevent NameError
speech = ""

# CUSTOM STYLING (Hides Streamlit UI for an 'App' look)
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top:-60px;}
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }
    </style>
    """, unsafe_allow_html=True)

# THE SOFTWARE FLASH (Safe way to light up the vial without crashing camera)
use_software_flash = st.sidebar.toggle("💡 Enable Software Flash")
if use_software_flash:
    st.markdown("""<style> .stApp { background-color: white !important; } .main-header { background-color: #f0f0f0; } h1, h2, h3, p { color: black !important; } </style>""", unsafe_allow_html=True)
    st.sidebar.info("UI is now White to provide light for the sample.")

st.markdown(f'<div class="main-header"><h1 style="color:white; margin:0;">⚖️ NCB FIELD COMPANION</h1><p style="color:#4E9F3D; margin:0; font-weight:bold;">Forensic Intelligence Support</p></div>', unsafe_allow_html=True)

model, meta = train_ncb_ai()

with st.sidebar:
    st.header("📋 Case Administration")
    off_id = st.text_input("Officer ID", "NCB-DEL-101")
    case_no = st.text_input("Case Reference", "F.No-2024/09")
    st.divider()
    st.write(f"Standard Time (IST): {get_india_time()}")

st.subheader("1. Sample Evidence Capture")
cam_img = st.camera_input("SCAN REAGENT VIAL")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    
    # Process Center Area
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    
    lab = rgb_to_lab_scaled(avg_rgb)
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    u_name = get_universal_name(avg_rgb)
    
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_c};">
            <h1 style="margin:0; color:white; font-size: 2.5em;">{u_name}</h1>
            <p style="margin:0; color:#AAA;"><b>HEX:</b> {hex_c.upper()} | <b>LAB:</b> {lab}</p>
        </div>
    """, unsafe_allow_html=True)

    # Prediction
    res_drug, res_ndps, conf = "No Match", "N/A", 0.0
    speech = f"Detected shade is {u_name}."

    if model and meta:
        probs = model.predict_proba([lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        
        if idx == 0: # Neutral detection
            st.warning("⚠️ RESULT: No drug reagent detected (Background Neutral).")
            speech += " No drug match found."
        elif conf > 75:
            res_drug, res_ndps = meta[0][idx], meta[1][idx]
            st.success(f"✅ AI MATCH: {res_drug} ({conf:.1f}% Confidence)")
            st.info(f"📜 Statute: {res_ndps}")
            speech += f" Result consistent with {res_drug} at {conf:.0f} percent confidence."
        else:
            st.warning("Inconclusive result. Low AI confidence.")
            speech += " Result is inconclusive."
    
    talk_back(speech)

    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔊 Repeat Audio"): talk_back(speech)
    with c2:
        pdf_bytes = generate_forensic_report({'time': get_india_time(), 'officer': off_id, 'case': case_no}, 
                                             {'name': u_name, 'hex': hex_c.upper(), 'lab': lab}, 
                                             res_drug, conf, res_ndps, img_hash)
        st.download_button("📄 Generate Report", pdf_bytes, "NCB_Report.pdf", "application/pdf")
