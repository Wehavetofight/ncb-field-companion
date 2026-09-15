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

# --- 1. CONFIGURATION ---
DB_FILE = "reagents.json"
CSV_FILE = "drug_reagents.csv"
IST = pytz.timezone('Asia/Kolkata')
NCB_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Narcotics_Control_Bureau_logo.png/220px-Narcotics_Control_Bureau_logo.png"

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# --- 2. DATASET CONVERTER (CSV to JSON) ---
def import_csv_to_json():
    """Reads CSV, converts HEX to CIELAB, and saves to reagents.json."""
    if not os.path.exists(CSV_FILE):
        return False
    try:
        df = pd.read_csv(CSV_FILE)
        new_db = {}
        for _, row in df.iterrows():
            # HEX to RGB
            h = row['hex_code'].lstrip('#')
            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            # RGB to Forensic CIELAB (L:0-100)
            pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
            lab_scaled = [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]
            
            entry_key = f"{row['reagent']}_{row['substance']}".lower().replace(" ", "_")
            new_db[entry_key] = {
                "reagent": row['reagent'],
                "target_compound": row['substance'],
                "target_lab": lab_scaled,
                "ndps_section": row['ndps_section']
            }
        with open(DB_FILE, "w") as f:
            json.dump(new_db, f, indent=2)
        return True
    except:
        return False

# --- 3. VOICE ENGINE ---
def talk_back(text):
    if text:
        components.html(f"""<script>window.speechSynthesis.cancel(); var msg = new SpeechSynthesisUtterance("{text}"); msg.lang = 'en-IN'; msg.rate = 0.9; window.speechSynthesis.speak(msg);</script>""", height=0)

# --- 4. AI MODEL TRAINING ---
@st.cache_resource
def train_ncb_ai():
    # Auto-import CSV if JSON is missing
    if not os.path.exists(DB_FILE):
        import_csv_to_json()
    
    try:
        with open(DB_FILE, "r") as f:
            db = json.load(f)
        X, y, labels, ndps_map = [], [], [], {}
        for key, data in db.items():
            t_lab = data.get('target_lab')
            if t_lab:
                for _ in range(120):
                    noise = np.random.normal(0, 2.0, 3) 
                    X.append(np.array(t_lab) + noise)
                    y.append(len(labels))
                ndps_map[len(labels)] = data.get('ndps_section', 'N/A')
                labels.append(data['target_compound'])
        
        model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
        model.fit(np.array(X), np.array(y))
        return model, (labels, ndps_map)
    except:
        return None, None

# --- 5. COLOR ANALYTICS ---
def get_universal_name(rgb):
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 12: 
        if r > 210: return "White"
        if r < 45: return "Black"
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
        return "Detected Color"

def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

# --- 6. PDF REPORT GENERATOR ---
def generate_ncb_report(case_info, color_data, result, conf, ndps, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        [Paragraph("<b>FORENSIC FIELD RECORD</b>", styles['Normal']), ""],
        ["TIMESTAMP (IST)", case_info['time']],
        ["OFFICER ID", case_info['officer']],
        ["CASE REF", case_info['case']],
        ["------------------", "------------------"],
        ["DETECTED COLOR", color_data['name']],
        ["HEX / CIELAB", f"{color_data['hex']} / {color_data['lab']}"],
        ["AI PREDICTION", result],
        ["CONFIDENCE", f"{conf:.1f}%"],
        ["LEGAL STATUTE", ndps],
        ["EVIDENCE HASH", img_hash],
    ]
    table = Table(data, colWidths=[160, 320])
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor("#002F6C")), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('PADDING', (0,0), (-1,-1), 10)]))
    doc.build([Paragraph("<b>NCB DIGITAL COMPANION REPORT</b>", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# --- 7. APP UI ---
st.set_page_config(page_title="NCB AI Shield", page_icon="⚖️")
st.markdown("""<style>.stApp { background-color: #0E1117; } .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top:-50px; } .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }</style>""", unsafe_allow_html=True)

st.markdown(f'<div class="main-header"><img src="{NCB_LOGO}" width="70"><h1 style="color:white; margin:0;">NCB FIELD COMPANION</h1></div>', unsafe_allow_html=True)
st.caption(f"Verifiable Forensic AI | IST: {get_india_time()}")

model, meta = train_ncb_ai()

with st.sidebar:
    st.header("📋 Admin & Records")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    case_ref = st.text_input("Case Number", "F.No-2024/09")
    st.divider()
    if st.button("📁 Import CSV Dataset"):
        if import_csv_to_json():
            st.success("Database Updated from CSV!")
            st.cache_resource.clear()
            st.rerun()
        else: st.error("CSV File not found.")

st.subheader("1. Evidence Capture")
cam_img = st.camera_input("Scan Reagent Vial")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    
    roi = img[img.shape[0]//2-15:img.shape[0]//2+15, img.shape[1]//2-15:img.shape[1]//2+15]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    lab = rgb_to_lab_scaled(avg_rgb)
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    u_name = get_universal_name(avg_rgb)
    
    st.markdown(f"""<div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_c};"><h1 style="margin:0; color:white; font-size: 2.5em;">{u_name}</h1><p style="margin:0; color:#AAA;"><b>HEX:</b> {hex_c.upper()} | <b>LAB:</b> {lab}</p></div>""", unsafe_allow_html=True)

    res_drug, res_ndps, conf = "No Match", "N/A", 0.0
    speech = f"Detected shade is {u_name}."

    if model and meta:
        probs = model.predict_proba([lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        if conf > 65:
            res_drug, res_ndps = meta[0][idx], meta[1][idx]
            st.success(f"⚖️ **AI MATCH:** {res_drug} ({conf:.1f}% Confidence)")
            st.info(f"📜 **Statute:** {res_ndps}")
            speech += f" Result consistent with {res_drug}."
        else: speech += " No drug match found."
    
    talk_back(speech)
    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔊 Repeat Audio"): talk_back(speech)
    with c2:
        rep = generate_ncb_report({'time': get_india_time(), 'officer': off_id, 'case': case_ref}, {'name': u_name, 'hex': hex_c.upper(), 'lab': lab}, res_drug, conf, res_ndps, img_hash)
        st.download_button("📄 Generate Report", rep, "NCB_Report.pdf", "application/pdf")
