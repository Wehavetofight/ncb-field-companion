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

# --- 1. CONFIGURATION & IDENTITY ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')
NCB_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Narcotics_Control_Bureau_logo.png/220px-Narcotics_Control_Bureau_logo.png"

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# --- 2. FORENSIC VOICE (TALK BACK) ---
def talk_back(text):
    """Voice synthesis for field officers."""
    components.html(f"""
        <script>
        window.speechSynthesis.cancel(); 
        var msg = new SpeechSynthesisUtterance("{text}");
        msg.lang = 'en-IN';
        msg.rate = 0.9;
        window.speechSynthesis.speak(msg);
        </script>
    """, height=0)

# --- 3. AI MODEL (LOGISTIC REGRESSION) ---
@st.cache_resource
def train_ncb_ai():
    """Trains AI using reagents.json. Fallbacks to internal Forensic Kit if file is empty."""
    db = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try: db = json.load(f)
            except: db = {}
    
    # Internal Forensic Kit (Fallback for SIH Demo)
    if len(db) < 2:
        db = {
            "Scott_Cocaine": {"target_compound": "Cocaine HCl", "target_lab": [38.0, 8.0, -48.0], "ndps": "Sec. 21"},
            "Marquis_Heroin": {"target_compound": "Heroin / Morphine", "target_lab": [24.0, 32.0, -18.0], "ndps": "Sec. 21"},
            "Marquis_Meth": {"target_compound": "Methamphetamine", "target_lab": [48.0, 42.0, 45.0], "ndps": "Sec. 22"},
            "Ehrlich_LSD": {"target_compound": "LSD / Indoles", "target_lab": [45.0, 38.0, -12.0], "ndps": "Sec. 22"},
            "Neutral": {"target_compound": "No Drug Detected", "target_lab": [60.0, 0.0, 0.0], "ndps": "N/A"}
        }

    try:
        X, y, labels, ndps_map = [], [], [], {}
        for key, data in db.items():
            t_lab = data.get('target_lab')
            if t_lab:
                for _ in range(150): # Augment with noise for shadows/glare
                    noise = np.random.normal(0, 2.5, 3) 
                    X.append(np.array(t_lab) + noise)
                    y.append(len(labels))
                ndps_map[len(labels)] = data.get('ndps_section', data.get('ndps', 'N/A'))
                labels.append(data['target_compound'])
        
        model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
        model.fit(X, y)
        return model, (labels, ndps_map)
    except:
        return None, None

# --- 4. COLOR ANALYTICS ---
def get_universal_name(rgb):
    """Standardized naming to remove human subjectivity."""
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 15: # Detect Neutrals
        if r > 200: return "Off-White"
        if r < 50: return "Charcoal"
        return "Neutral Gray"
    try:
        min_dist = float('inf')
        closest_name = "Custom Shade"
        for hex_val, name in webcolors.CSS3_HEX_TO_NAMES.items():
            r_c, g_c, b_c = webcolors.hex_to_rgb(hex_val)
            dist = (r_c - r)**2 + (g_c - g)**2 + (b_c - b)**2
            if dist < min_dist:
                min_dist = dist
                closest_name = name
        return closest_name.title().replace('Grey', 'Gray')
    except:
        return "Detected Shade"

def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

# --- 5. VERIFIABLE PDF GENERATOR ---
def generate_ncb_report(case_info, color_data, result, ndps, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        [Paragraph("<b>FORENSIC FIELD RECORD</b>", styles['Normal']), ""],
        ["NCB DEPT", "NARCOTICS CONTROL BUREAU"],
        ["TIMESTAMP", case_info['time']],
        ["OFFICER ID", case_info['officer']],
        ["CASE REF", case_info['case']],
        ["------------------", "------------------"],
        ["DETECTED COLOR", color_data['name']],
        ["HEX / CIELAB", f"{color_data['hex']} / {color_data['lab']}"],
        ["AI RESULT", result],
        ["LEGAL STATUTE", ndps],
        ["------------------", "------------------"],
        ["EVIDENCE HASH", img_hash],
    ]
    table = Table(data, colWidths=[160, 320])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#002F6C")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    doc.build([Paragraph("<b>NCB DIGITAL COMPANION REPORT</b>", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# --- 6. APP UI ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")

# Professional Government Styling
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }
    </style>
    """, unsafe_allow_html=True)

# App Header
st.markdown(f"""
    <div class="main-header">
        <img src="{NCB_LOGO}" width="80">
        <h1 style="color:white; margin:0;">NCB FIELD COMPANION</h1>
        <p style="color:#4E9F3D; margin:0; font-weight:bold;">SIH 26231: Digital Evidence Support</p>
    </div>
    """, unsafe_allow_html=True)

st.caption(f"Verifiable Record Log | {get_india_time()}")

# AI Model Init
model, meta = train_ncb_ai()

with st.sidebar:
    st.header("📋 Officer Registry")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    case_ref = st.text_input("Case Number", "F.No-" + datetime.now(IST).strftime("%Y/%m"))
    st.divider()
    if st.button("🔄 Sync AI & Database"):
        st.cache_resource.clear()
        st.rerun()

# --- STEP 1: CAPTURE ---
st.subheader("1. Sample Evidence Capture")
cam_img = st.camera_input("Position reagent vial in center")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    
    # Extract Color
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    
    lab = rgb_to_lab_scaled(avg_rgb)
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    u_name = get_universal_name(avg_rgb)
    
    # --- STEP 2: ANALYSIS ---
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_c};">
            <h1 style="margin:0; color:white; font-size: 2.8em;">{u_name}</h1>
            <p style="margin:0; color:#AAA;"><b>HEX:</b> {hex_c.upper()} | <b>LAB:</b> {lab}</p>
        </div>
    """, unsafe_allow_html=True)

    # Prediction
    res_drug, res_ndps, conf = "No Match", "N/A", 0.0
    if model and meta:
        probs = model.predict_proba([lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        if conf > 65:
            res_drug, res_ndps = meta[0][idx], meta[1][idx]
            st.success(f"⚖️ **POSS. MATCH:** {res_drug} ({conf:.1f}% AI Confidence)")
            st.info(f"📜 **Statute:** {res_ndps}")
            speech = f"Analysis complete. {conf:.0f} percent probability of {res_drug}."
        else:
            st.warning("Low confidence. No reagent match identified.")
            speech = f"Detected shade is {u_name}. No drug match found."
    
    talk_back(speech)

    # --- STEP 3: DOCUMENTATION ---
    st.write("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔊 Repeat Audio"): talk_back(speech)
    with col2:
        rep_bytes = generate_ncb_report({'time': get_india_time(), 'officer': off_id, 'case': case_ref}, 
                                       {'name': u_name, 'hex': hex_c.upper(), 'lab': lab}, 
                                       res_drug, res_ndps, img_hash)
        st.download_button("📄 Generate Report", rep_bytes, f"NCB_Record_{img_hash}.pdf", "application/pdf")
