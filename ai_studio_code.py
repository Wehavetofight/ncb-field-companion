import streamlit as st
import cv2
import numpy as np
import hashlib
import json
import os
import pytz
import webcolors
import pandas as pd
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
DB_FILE = "reagents.json"
CSV_FILE = "drug_reagents.csv"
IST = pytz.timezone('Asia/Kolkata')
NCB_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Narcotics_Control_Bureau_logo.png/220px-Narcotics_Control_Bureau_logo.png"

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# ============================================================
# 2. HARDWARE & SECURITY (Flashlight & Auto-Kill)
# ============================================================
def inject_security_logic(torch_on):
    torch_js = "true" if torch_on else "false"
    components.html(f"""
        <script>
        async function setTorch(state) {{
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{video: {{facingMode: "environment"}}}});
                const track = stream.getVideoTracks()[0];
                if (track.getCapabilities().torch) {{
                    await track.applyConstraints({{advanced: [{{torch: state}}]}});
                }}
            }} catch (e) {{ console.log("Torch access denied"); }}
        }}
        setTorch({torch_js});

        document.addEventListener("visibilitychange", () => {{
            if (document.visibilityState === 'hidden') {{ window.location.reload(); }}
        }});
        </script>
    """, height=0)

# ============================================================
# 3. VOICE ENGINE (Talk Back)
# ============================================================
def talk_back(text):
    if text:
        components.html(f"""
            <script>
            window.speechSynthesis.cancel(); 
            var msg = new SpeechSynthesisUtterance("{text}");
            msg.lang = 'en-IN'; msg.rate = 0.9;
            window.speechSynthesis.speak(msg);
            </script>
        """, height=0)

# ============================================================
# 4. AI MODEL TRAINING (Logic with Neutral Class & File Loading)
# ============================================================
@st.cache_resource
def train_ncb_ai():
    # 1. Try to load from your Database files first
    db = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: db = json.load(f)
    
    # 2. Fallback SIH Starter Kit (If file is empty or missing)
    if len(db) < 2:
        db = {
            "Cocaine": {"target_lab": [38, 8, -48], "ndps": "Sec. 21 (Cocaine)"},
            "Heroin": {"target_lab": [24, 32, -18], "ndps": "Sec. 21 (Opiates)"},
            "Meth": {"target_lab": [48, 42, 45], "ndps": "Sec. 22 (Psychotropic)"},
            "Cannabis": {"target_lab": [28, 22, -28], "ndps": "Sec. 20 (Cannabis)"},
            "LSD": {"target_lab": [45, 38, -12], "ndps": "Sec. 22 (Psychotropic)"}
        }
    
    X, y, labels, ndps_map = [], [], [], {}
    
    # SAFEGUARD: THE "NEUTRAL" CLASS (Class 0)
    # Prevents "The Wall" from being detected as a drug
    neutrals = [[65,0,0], [95,0,0], [25,0,0], [75,2,4], [55,1,1]] 
    for n_color in neutrals:
        for _ in range(120):
            X.append(np.array(n_color) + np.random.normal(0, 1.8, 3))
            y.append(0)
    labels.append("Neutral (No Drug Detected)")

    # 3. Load Forensic profiles
    for key, data in db.items():
        idx = len(labels)
        t_lab = data.get('target_lab', data.get('lab'))
        if t_lab:
            for _ in range(150):
                noise = np.random.normal(0, 2.2, 3) 
                X.append(np.array(t_lab) + noise)
                y.append(idx)
            ndps_map[idx] = data.get('ndps_section', data.get('ndps', 'N/A'))
            labels.append(data.get('target_compound', key))
        
    model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
    model.fit(np.array(X), np.array(y))
    return model, (labels, ndps_map)

# ============================================================
# 5. FORENSIC COLOR MATH
# ============================================================
def get_universal_name(rgb):
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 12: return "Neutral Gray/White"
    try:
        min_dist = float('inf')
        closest_name = "Detected Shade"
        for hex_val, name in webcolors.CSS3_HEX_TO_NAMES.items():
            r_c, g_c, b_c = webcolors.hex_to_rgb(hex_val)
            dist = np.sqrt((r_c - r)**2 + (g_c - g)**2 + (b_c - b)**2)
            if dist < min_dist:
                min_dist = dist
                closest_name = name
        return closest_name.title().replace('Grey', 'Gray')
    except: return "Custom Shade"

def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

# ============================================================
# 6. PDF GENERATOR
# ============================================================
def generate_forensic_report(case_info, color_data, result, conf, ndps, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        [Paragraph("<b>FIELD EVIDENCE RECORD</b>", styles['Normal']), ""],
        ["TIMESTAMP (IST)", case_info['time']],
        ["OFFICER ID", case_info['officer']],
        ["CASE REF", case_info['case']],
        ["------------------", "------------------"],
        ["DETECTED COLOR", color_data['name']],
        ["HEX / CIELAB", f"{color_data['hex']} / {color_data['lab']}"],
        ["AI PREDICTION", result],
        ["CONFIDENCE", f"{conf:.1f}%"],
        ["NDPS STATUTE", ndps],
        ["EVIDENCE HASH", img_hash],
    ]
    table = Table(data, colWidths=[160, 320])
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor("#002F6C")), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('PADDING', (0,0), (-1,-1), 10)]))
    doc.build([Paragraph("<b>NARCOTICS CONTROL BUREAU</b>", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# ============================================================
# 7. APP UI LAYOUT
# ============================================================
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top:-60px;}
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }
    </style>
    """, unsafe_allow_html=True)

st.markdown(f'<div class="main-header"><h1 style="color:white; margin:0;">⚖️ NCB FIELD COMPANION</h1><p style="color:#4E9F3D; margin:0; font-weight:bold;">Forensic Intelligence Support</p></div>', unsafe_allow_html=True)

model, meta = train_ncb_ai()

with st.sidebar:
    st.header("📋 Administration")
    off_id = st.text_input("Officer ID", "NCB-DEL-101")
    case_no = st.text_input("Case Reference", "F.No-" + datetime.now(IST).strftime("%Y/%m"))
    st.divider()
    flash = st.toggle("🔦 Turn on Flashlight")
    st.divider()
    st.write(f"System IST: {get_india_time()}")

inject_security_logic(flash)

st.subheader("1. Evidence Capture")
cam_img = st.camera_input("SCAN REAGENT VIAL")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    
    # Process center ROI
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    lab = rgb_to_lab_scaled(avg_rgb)
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    u_name = get_universal_name(avg_rgb)
    
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_c};">
            <h1 style="margin:0; color:white; font-size: 2.8em;">{u_name}</h1>
            <p style="margin:0; color:#AAA;"><b>HEX:</b> {hex_c.upper()} | <b>LAB:</b> {lab}</p>
        </div>
    """, unsafe_allow_html=True)

    # PREDICTION
    res_drug, res_ndps, conf = "No Match", "N/A", 0.0
    speech = f"Detected shade is {u_name}."

    if model and meta:
        probs = model.predict_proba([lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        
        if idx == 0: # Neutral detection
            st.warning("⚠️ RESULT: No drug reagent detected (Neutral/Background).")
            speech += " No drug match found."
        elif conf > 70:
            res_drug, res_ndps = meta[0][idx], meta[1][idx]
            st.success(f"✅ AI MATCH: {res_drug} ({conf:.1f}% Confidence)")
            st.info(f"📜 Statute: {res_ndps}")
            speech += f" Result consistent with {res_drug}."
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
        st.download_button("📄 Generate Report", pdf_bytes, f"NCB_Record_{img_hash}.pdf", "application/pdf")
