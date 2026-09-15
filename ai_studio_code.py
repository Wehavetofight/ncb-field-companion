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

# PDF Libraries
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# --- 1. CONFIGURATION & TIME ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# --- 2. VOICE ENGINE (Talk Back) ---
def talk_back(text):
    """Triggers automated forensic voice announcement."""
    components.html(f"""
        <script>
        window.speechSynthesis.cancel(); 
        var msg = new SpeechSynthesisUtterance("{text}");
        msg.lang = 'en-IN';
        msg.rate = 0.9;
        window.speechSynthesis.speak(msg);
        </script>
    """, height=0)

# --- 3. AI MODEL TRAINING (Logistic Regression) ---
@st.cache_resource
def train_forensic_model():
    """Trains AI. Fallbacks to Starter Kit if reagents.json is missing."""
    db = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try: db = json.load(f)
            except: db = {}
    
    # STARTER KIT: These load automatically if your JSON is empty
    if len(db) < 2:
        db = {
            "Scott_Cocaine": {"target_compound": "Cocaine HCl", "target_lab": [38.0, 8.0, -48.0], "ndps_section": "Sec. 21"},
            "Marquis_Heroin": {"target_compound": "Heroin / Morphine", "target_lab": [24.0, 32.0, -18.0], "ndps_section": "Sec. 21"},
            "Marquis_Amphetamine": {"target_compound": "Amphetamine / Meth", "target_lab": [48.0, 42.0, 45.0], "ndps_section": "Sec. 22"},
            "Duquenois_THC": {"target_compound": "Cannabis / THC", "target_lab": [28.0, 22.0, -28.0], "ndps_section": "Sec. 20"},
            "Mandelin_Meth": {"target_compound": "Methamphetamine", "target_lab": [42.0, -28.0, 22.0], "ndps_section": "Sec. 22"},
            "Mecke_Opiates": {"target_compound": "Opiates / Oxycodone", "target_lab": [35.0, -18.0, 15.0], "ndps_section": "Sec. 21"},
            "Ehrlich_LSD": {"target_compound": "LSD / Indoles", "target_lab": [45.0, 38.0, -12.0], "ndps_section": "Sec. 22"},
            "Simons_Meth": {"target_compound": "Methamphetamine", "target_lab": [45.0, -4.0, -45.0], "ndps_section": "Sec. 22"}
        }

    try:
        X_train, y_train, class_labels, ndps_map = [], [], [], {}
        for key, data in db.items():
            target_lab = data.get('target_lab')
            if target_lab:
                for _ in range(150): # Augment for lighting noise
                    noise = np.random.normal(0, 2.5, 3) 
                    X_train.append(np.array(target_lab) + noise)
                    y_train.append(len(class_labels))
                ndps_map[len(class_labels)] = data.get('ndps_section', 'N/A')
                class_labels.append(data['target_compound'])
        
        model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
        model.fit(X_train, y_train)
        return model, (class_labels, ndps_map)
    except:
        return None, None

# --- 4. COLOR MATH ---
def get_universal_name(rgb):
    try:
        r, g, b = [int(x) for x in rgb]
        # Neutral Check
        diff = max(r, g, b) - min(r, g, b)
        if diff < 15:
            if r > 200: return "Pure White"
            if r < 50: return "Jet Black"
            return "Neutral Gray"
            
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
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB2Lab)
    l, a, b = pixel_lab[0][0]
    return [round(float(l * (100/255)), 1), round(float(a - 128), 1), round(float(b - 128), 1)]

# --- 5. FORENSIC PDF GENERATOR ---
def generate_ncb_pdf(case_info, color_data, result_text, ndps, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        [Paragraph("<b>FIELD DRUG TEST RECORD</b>", styles['Normal']), ""],
        ["STATUS", "PRESUMPTIVE SCREENING ONLY"],
        ["TIMESTAMP (IST)", case_info['time']],
        ["OFFICER ID", case_info['officer']],
        ["CASE REFERENCE", case_info['case']],
        ["------------------", "------------------"],
        ["DETECTED SHADE", color_data['name']],
        ["HEX CODE", color_data['hex']],
        ["CIELAB VALUES", f"{color_data['lab']}"],
        ["------------------", "------------------"],
        ["AI PREDICTION", result_text],
        ["NDPS PROVISION", ndps],
        ["EVIDENCE HASH", img_hash],
    ]
    table = Table(data, colWidths=[160, 320])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#002F6C")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    doc.build([Paragraph("<b>NARCOTICS CONTROL BUREAU</b>", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# --- 6. APP MAIN UI ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")
st.title("⚖️ NCB Field Companion")
st.caption(f"Forensic AI Unit | IST: {get_india_time()}")

# Initialize AI
ml_model, meta = train_forensic_model()

with st.sidebar:
    st.header("📋 Case Details")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    case_no = st.text_input("Case Reference", "F.No-" + datetime.now(IST).strftime("%Y/%m"))
    st.divider()
    if st.button("Refresh AI & Data"):
        st.cache_resource.clear()
        st.rerun()

st.subheader("1. Optical Evidence Capture")
camera_img = st.camera_input("Scan Reagent Sample")

if camera_img:
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(camera_img.getvalue()).hexdigest()[:16]
    
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1]
    
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_val};">
            <h1 style="margin:0; color:white; font-size: 2.8em;">{u_name}</h1>
            <p style="margin:0; color:#AAA; font-size: 1.2em;">HEX: <b>{hex_val.upper()}</b></p>
            <p style="margin:0; color:#4E9F3D; font-weight:bold;">CIELAB Standards: L:{center_lab[0]} a:{center_lab[1]} b:{center_lab[2]}</p>
        </div>
    """, unsafe_allow_html=True)

    # --- AI PREDICTION ---
    final_drug = "No Match Found"
    final_ndps = "N/A"
    confidence = 0.0
    speech_text = f"Detected shade is {u_name}."

    if ml_model and meta:
        probs = ml_model.predict_proba([center_lab])[0]
        idx = np.argmax(probs)
        confidence = probs[idx] * 100
        
        if confidence > 65:
            final_drug = meta[0][idx]
            final_ndps = meta[1][idx]
            st.success(f"⚖️ **AI MATCH:** {final_drug} ({confidence:.1f}% Confidence)")
            st.info(f"📜 **NDPS Provision:** {final_ndps}")
            speech_text += f" Match found. Consistent with {final_drug}."
        else:
            speech_text += " No matching reagent found."
    
    talk_back(speech_text)

    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔊 Repeat Audio"): talk_back(speech_text)
    with c2:
        c_info = {'time': get_india_time(), 'officer': off_id, 'case': case_no}
        col_info = {'name': u_name, 'hex': hex_val.upper(), 'lab': center_lab}
        pdf_bytes = generate_ncb_pdf(c_info, col_info, final_drug, final_ndps, img_hash)
        st.download_button(label="📄 Generate Report", data=pdf_bytes, file_name=f"NCB_Report.pdf", mime="application/pdf")
