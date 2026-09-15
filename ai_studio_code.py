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

# --- 1. CONFIGURATION ---
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
    """Trains AI using your reagents.json profiles."""
    if not os.path.exists(DB_FILE):
        return None, None
    try:
        with open(DB_FILE, "r") as f:
            db = json.load(f)
        
        X_train, y_train, class_labels, ndps_map = [], [], [], {}
        
        if len(db) < 2:
            return "DATA_INSUFFICIENT", None

        for key, data in db.items():
            target_lab = data.get('target_lab')
            if target_lab:
                # Synthetic Augmentation: Create 150 variants per drug to handle lighting
                for _ in range(150):
                    noise = np.random.normal(0, 2.5, 3) 
                    X_train.append(np.array(target_lab) + noise)
                    y_train.append(len(class_labels))
                
                ndps_map[len(class_labels)] = data.get('ndps_section', 'N/A')
                class_labels.append(data['target_compound'])
        
        model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
        model.fit(X_train, y_train)
        return model, (class_labels, ndps_map)
    except Exception as e:
        return f"ERROR: {str(e)}", None

# --- 4. FORENSIC COLOR MATH ---
def get_universal_name(rgb):
    try:
        r, g, b = [int(x) for x in rgb]
        min_dist = float('inf')
        closest_name = "Unknown Shade"
        for hex_val, name in webcolors.CSS3_HEX_TO_NAMES.items():
            r_c, g_c, b_c = webcolors.hex_to_rgb(hex_val)
            dist = np.sqrt((r_c - r)**2 + (g_c - g)**2 + (b_c - b)**2)
            if dist < min_dist:
                min_dist = dist
                closest_name = name
        return closest_name.title().replace('Grey', 'Gray')
    except:
        return "Detected Shade"

def rgb_to_lab_scaled(rgb):
    """Converts RGB to standard CIELAB scale (L:0-100)."""
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB2Lab)
    l, a, b = pixel_lab[0][0]
    # Scaling OpenCV's 0-255 Lab to standard Forensic Lab 0-100
    return [round(float(l * (100/255)), 1), round(float(a - 128), 1), round(float(b - 128), 1)]

# --- 5. PDF REPORT GENERATOR ---
def generate_ncb_pdf(case_info, color_data, result_text, ndps, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    data = [
        [Paragraph("<b>FIELD DRUG TEST RECORD</b>", styles['Normal']), ""],
        ["STATUS", "PRESUMPTIVE SCREENING"],
        ["TIMESTAMP (IST)", case_info['time']],
        ["OFFICER ID", case_info['officer']],
        ["CASE REFERENCE", case_info['case']],
        ["------------------", "------------------"],
        ["DETECTED SHADE", color_data['name']],
        ["HEX CODE", color_data['hex']],
        ["CIELAB (L, a, b)", f"{color_data['lab']}"],
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
    
    elements = [
        Paragraph("<b>NARCOTICS CONTROL BUREAU</b>", styles['Title']),
        Paragraph("<para align=center>Government of India</para>", styles['Normal']),
        Spacer(1, 20),
        table,
        Spacer(1, 25),
        Paragraph("<i>Note: This is a presumptive digital report. Confirmatory laboratory analysis (GC-MS) is required for legal proceedings.</i>", styles['Normal'])
    ]
    doc.build(elements)
    return buffer.getvalue()

# --- 6. APP MAIN UI ---
st.set_page_config(page_title="NCB AI Shield", page_icon="⚖️")
st.title("⚖️ NCB Field Companion")
st.caption(f"Forensic AI Unit | IST: {get_india_time()}")

# Initialize AI
ml_model, meta = train_forensic_model()

with st.sidebar:
    st.header("📋 Case Details")
    off_id = st.text_input("Officer ID", "NCB-OFF-101")
    case_no = st.text_input("Case Reference", "F.No-" + datetime.now(IST).strftime("%Y/%m"))
    st.divider()
    if st.button("Re-train AI Model"):
        st.cache_resource.clear()
        st.rerun()

st.subheader("1. Optical Evidence Capture")
camera_img = st.camera_input("Position sample in the center of the frame")

if camera_img:
    # --- Image Processing ---
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(camera_img.getvalue()).hexdigest()[:16]
    
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1]
    
    # Forensic Coordinates
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    # --- UI DISPLAY ---
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

    if isinstance(ml_model, str):
        st.warning("⚠️ AI training requires at least 2 drugs in reagents.json.")
    elif ml_model and meta:
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
            st.warning("Result: Universal color recorded. No high-confidence drug match.")
            speech_text += " No matching drug reagent found."
    
    # Voice Trigger
    talk_back(speech_text)

    # --- ACTIONS ---
    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔊 Repeat Audio"): talk_back(speech_text)
    with c2:
        c_info = {'time': get_india_time(), 'officer': off_id, 'case': case_no}
        col_info = {'name': u_name, 'hex': hex_val.upper(), 'lab': center_lab}
        pdf_bytes = generate_ncb_pdf(c_info, col_info, final_drug, final_ndps, img_hash)
        st.download_button(label="📄 Generate Report", data=pdf_bytes, file_name=f"NCB_Forensic_Report.pdf", mime="application/pdf")
