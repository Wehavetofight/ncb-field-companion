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

# --- 2. TALK BACK (VOICE) ENGINE ---
def talk_back(text):
    """Triggers the browser to speak the forensic result."""
    components.html(f"""
        <script>
        window.speechSynthesis.cancel(); 
        var msg = new SpeechSynthesisUtterance("{text}");
        msg.lang = 'en-IN';
        msg.rate = 0.9;
        window.speechSynthesis.speak(msg);
        </script>
    """, height=0)

# --- 3. ML MODEL TRAINING (LOGISTIC REGRESSION) ---
@st.cache_resource
def train_logistic_model():
    if not os.path.exists(DB_FILE):
        return None, None
    try:
        with open(DB_FILE, "r") as f:
            db = json.load(f)
        X_train, y_train, class_labels, ndps_map = [], [], [], {}
        for key, data in db.items():
            target_lab = data.get('target_lab')
            if target_lab:
                for _ in range(150): # Data Augmentation for noise
                    noise = np.random.normal(0, 2.0, 3) 
                    X_train.append(np.array(target_lab) + noise)
                    y_train.append(len(class_labels))
                ndps_map[len(class_labels)] = data.get('ndps_section', 'N/A')
                class_labels.append(data['target_compound'])
        if not X_train: return None, None
        model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
        model.fit(X_train, y_train)
        return model, (class_labels, ndps_map)
    except:
        return None, None

# --- 4. COLOR & FORENSIC MATH ---
def get_universal_name(rgb):
    try:
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
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
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB2Lab)
    l, a, b = pixel_lab[0][0].astype(float)
    return [round(l * (100/255), 1), round(a - 128, 1), round(b - 128, 1)]

# --- 5. FORENSIC PDF GENERATOR ---
def generate_forensic_pdf(case_info, color_data, match_info, ndps_info, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        [Paragraph("<b>FIELD DRUG SCREENING RECORD</b>", styles['Normal']), ""],
        ["STATUS", "PRESUMPTIVE SCREENING ONLY"],
        ["TIMESTAMP (IST)", case_info['time']],
        ["OFFICER ID", case_info['officer']],
        ["CASE REFERENCE", case_info['case']],
        ["DETECTED SHADE", color_data['name']],
        ["HEX CODE", color_data['hex']],
        ["CIELAB VALUES", f"L:{color_data['lab'][0]} a:{color_data['lab'][1]} b:{color_data['lab'][2]}"],
        ["POSS. MATCH", match_info],
        ["NDPS PROVISION", ndps_info],
        ["RECORD HASH", img_hash],
    ]
    table = Table(data, colWidths=[160, 320])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#002F6C")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    doc.build([Paragraph("<b>NARCOTICS CONTROL BUREAU</b>", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# --- 6. MAIN APP INTERFACE ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")
st.title("⚖️ NCB Field Companion")
st.write(f"**Forensic Intelligence Unit** | {get_india_time()}")

# ML Training
ml_model, meta = train_logistic_model()

with st.sidebar:
    st.header("📋 Case Records")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    case_ref = st.text_input("Case No.", "F.No-" + datetime.now(IST).strftime("%Y/%m/%d"))
    if st.button("Refresh AI Model"):
        st.cache_resource.clear()
        st.rerun()

st.subheader("1. Optical Evidence Capture")
camera_img = st.camera_input("Place the sample vial/strip in center")

if camera_img:
    # Processing
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(camera_img.getvalue()).hexdigest()[:16]
    
    h, w, _ = img.shape
    roi = img[h//2-10:h//2+10, w//2-10:w//2+10]
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1]
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""<div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_val};">
        <h1 style="margin:0; color:white;">{u_name}</h1>
        <p style="margin:0; color:#AAA;">HEX: {hex_val.upper()} | LAB: {center_lab}</p>
    </div>""", unsafe_allow_html=True)

    # ML Prediction
    match_found = False
    predicted_drug = "No Match"
    ndps_note = "N/A"
    
    if ml_model and meta:
        probs = ml_model.predict_proba([center_lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        if conf > 65:
            predicted_drug = meta[0][idx]
            ndps_note = meta[1][idx]
            st.success(f"✅ **POSS. MATCH:** {predicted_drug} ({conf:.1f}% Confidence)")
            st.info(f"📜 **NDPS Provision:** {ndps_note}")
            match_found = True
            voice_txt = f"Detected {u_name}. Result consistent with {predicted_drug}."
        else:
            voice_txt = f"Detected {u_name}. No reagent match found."
    
    talk_back(voice_txt)

    # 3. Actions
    st.write("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔊 Repeat Audio"):
            talk_back(voice_txt)
    with col2:
        case_info = {'time': get_india_time(), 'officer': off_id, 'case': case_ref}
        color_info = {'name': u_name, 'hex': hex_val.upper(), 'lab': center_lab}
        pdf_bytes = generate_forensic_pdf(case_info, color_info, predicted_drug, ndps_note, img_hash)
        st.download_button(label="📄 Generate Report", data=pdf_bytes, file_name=f"NCB_Report_{img_hash[:8]}.pdf", mime="application/pdf")

with st.expander("🛠️ Admin: Register Benchmark"):
    st.text_input("Substance Name")
    st.button("Save to Database")
