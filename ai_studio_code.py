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

# --- 1. CONFIGURATION ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')
# Stable Logo Link
NCB_LOGO = "https://raw.githubusercontent.com/streamlit/st-user-manual/master/NCB_Logo.png" # Standard placeholder or your own URL

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

def talk_back(text):
    if text:
        components.html(f"""<script>window.speechSynthesis.cancel(); var m=new SpeechSynthesisUtterance("{text}"); m.lang='en-IN'; m.rate=0.9; window.speechSynthesis.speak(m);</script>""", height=0)

# --- 2. AI MODEL TRAINING (ROBUST) ---
@st.cache_resource
def train_ncb_ai():
    db = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try: db = json.load(f)
            except: db = {}
    
    # FORCED STARTER KIT (If JSON is empty or file missing)
    if len(db) < 2:
        db = {
            "Cocaine": {"target_compound": "Cocaine (Scott Reagent)", "target_lab": [38.0, 8.0, -48.0], "ndps": "Sec. 21"},
            "Heroin": {"target_compound": "Heroin (Marquis Reagent)", "target_lab": [24.0, 32.0, -18.0], "ndps": "Sec. 21"},
            "Meth": {"target_compound": "Methamphetamine (Marquis)", "target_lab": [48.0, 42.0, 45.0], "ndps": "Sec. 22"},
            "Cannabis": {"target_compound": "Cannabis (Duquenois)", "target_lab": [28.0, 22.0, -28.0], "ndps": "Sec. 20"},
            "LSD": {"target_compound": "LSD (Ehrlich)", "target_lab": [45.0, 38.0, -12.0], "ndps": "Sec. 22"},
            "Neutral": {"target_compound": "No Match / Negative", "target_lab": [70.0, 0.0, 0.0], "ndps": "N/A"}
        }

    X, y, labels, ndps_map = [], [], [], {}
    for key, data in db.items():
        t_lab = data.get('target_lab')
        if t_lab:
            for _ in range(120): # Noise for shadows
                noise = np.random.normal(0, 2.0, 3) 
                X.append(np.array(t_lab) + noise)
                y.append(len(labels))
            ndps_map[len(labels)] = data.get('ndps_section', data.get('ndps', 'N/A'))
            labels.append(data['target_compound'])
    
    model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
    model.fit(X, y)
    return model, (labels, ndps_map)

# --- 3. COLOR ANALYTICS ---
def get_universal_name(rgb):
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 12: 
        if r > 215: return "Off-White"
        if r < 45: return "Charcoal"
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
    except: return "Detected Color"

def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

def generate_pdf(case, color, result, conf, ndps, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        [Paragraph("<b>FORENSIC FIELD RECORD</b>", styles['Normal']), ""],
        ["TIMESTAMP", case['time']], ["OFFICER ID", case['officer']], ["CASE REF", case['case']],
        ["DETECTED COLOR", color['name']], ["HEX/LAB", f"{color['hex']} / {color['lab']}"],
        ["AI PREDICTION", result], ["CONFIDENCE", f"{conf:.1f}%"], ["NDPS PROVISION", ndps], ["EVIDENCE HASH", img_hash]
    ]
    table = Table(data, colWidths=[160, 320])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor("#002F6C")),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.5,colors.grey),('PADDING',(0,0),(-1,-1),10)]))
    doc.build([Paragraph("<b>NCB DIGITAL COMPANION REPORT</b>", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# --- 4. APP UI ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top: -55px;}
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }
    </style>
    """, unsafe_allow_html=True)

st.markdown(f'<div class="main-header"><h1 style="color:white; margin:0;">⚖️ NCB FIELD COMPANION</h1><p style="color:#4E9F3D; margin:0; font-weight:bold;">Forensic Intelligence Support</p></div>', unsafe_allow_html=True)

model, meta = train_ncb_ai()

with st.sidebar:
    st.header("📋 Case Details")
    off_id = st.text_input("Officer ID", "NCB-DEL-101")
    case_no = st.text_input("Case Reference", "F.No-" + datetime.now(IST).strftime("%Y/%m"))
    st.divider()
    st.info("The AI removes subjectivity from visual reagent tests.")

# --- CAMERA BLOCK ---
cam_img = st.camera_input("SCAN TEST VIAL")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    
    # Visual Target Feedback
    h, w, _ = img.shape
    r_size = 25 # Box size
    cx, cy = w//2, h//2
    
    # Create the Analysis Display Image
    display_img = img.copy()
    cv2.rectangle(display_img, (cx-r_size, cy-r_size), (cx+r_size, cy+r_size), (0, 255, 0), 2)
    st.image(cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB), caption="Sample Target Area (Green Box)")
    
    # Process Color from Target Box
    roi = img[cy-r_size:cy+r_size, cx-r_size:cx+r_size]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    lab = rgb_to_lab_scaled(avg_rgb)
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    u_name = get_universal_name(avg_rgb)
    
    # RESULTS UI
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_c};">
            <h1 style="margin:0; color:white; font-size: 2.5em;">{u_name}</h1>
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
        if conf > 65:
            res_drug, res_ndps = meta[0][idx], meta[1][idx]
            st.success(f"⚖️ **AI MATCH:** {res_drug} ({conf:.1f}% Confidence)")
            st.info(f"📜 **Provision:** {res_ndps}")
            speech += f" Result consistent with {res_drug}."
        else:
            st.warning("Low confidence. No reagent match found.")
            speech += " No matching drug reagent found."
    
    talk_back(speech)

    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔊 Repeat Audio"): talk_back(speech)
    with c2:
        rep_bytes = generate_pdf({'time': get_india_time(), 'officer': off_id, 'case': case_no}, 
                                {'name': u_name, 'hex': hex_c.upper(), 'lab': lab}, 
                                res_drug, conf, res_ndps, img_hash)
        st.download_button("📄 Download Report", rep_bytes, "NCB_Report.pdf", "application/pdf")
