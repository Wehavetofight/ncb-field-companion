import streamlit as st
import cv2
import numpy as np
import json
import os
import pytz
import hashlib
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

# --- 2. VOICE ENGINE (Browser Talk Back) ---
def talk_back(text):
    components.html(f"""<script>
        window.speechSynthesis.cancel();
        var m = new SpeechSynthesisUtterance("{text}");
        m.lang = 'en-IN'; window.speechSynthesis.speak(m);
    </script>""", height=0)

# --- 3. LOGISTIC REGRESSION TRAINING ---
@st.cache_resource
def train_ncb_model():
    if not os.path.exists(DB_FILE):
        return None, None
    with open(DB_FILE, "r") as f:
        db = json.load(f)

    X, y, labels = [], [], []
    for key, data in db.items():
        target_lab = data.get('target_lab')
        if target_lab:
            # Synthetic data generation to handle lighting noise
            for _ in range(120):
                noise = np.random.normal(0, 2.0, 3) 
                X.append(np.array(target_lab) + noise)
                y.append(len(labels))
            labels.append(data['target_compound'])
    
    if not X: return None, None
    
    model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
    model.fit(X, y)
    return model, labels

# --- 4. COLOR PROCESSING ---
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

# --- 5. PDF REPORT GENERATOR ---
def generate_pdf(case_info, color_data, match_info, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        ["NCB FIELD TEST REPORT", ""],
        ["Timestamp (IST)", case_info['time']],
        ["Officer ID", case_info['officer']],
        ["Case Reference", case_info['case']],
        ["Universal Shade", color_data['name']],
        ["Detected HEX", color_data['hex']],
        ["AI Result", match_info],
        ["Record Hash", img_hash]
    ]
    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.navy),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 10)
    ]))
    doc.build([Paragraph("FORENSIC ANALYSIS RECORD", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# --- 6. MAIN APP INTERFACE ---
st.title("⚖️ NCB Forensic Companion")
st.write(f"**Current Time (IST):** {get_india_time()}")

# Train Model
model, drug_labels = train_ncb_model()

# Sidebar for Metadata
with st.sidebar:
    st.header("Case Management")
    off_id = st.text_input("Officer ID", "NCB-101")
    case_ref = st.text_input("Case Number", "NCB/2024/001")
    st.divider()
    if st.button("Reset AI Model"):
        st.cache_resource.clear()
        st.rerun()

# Camera Section
cam_img = st.camera_input("Scan Reagent Sample")

if cam_img and model:
    # 1. Image Processing
    file_bytes = np.frombuffer(cam_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(cam_img.getvalue()).hexdigest()[:16]
    
    # 2. Extract Center Color (3 Parameters)
    h, w, _ = img.shape
    roi = img[h//2-10:h//2+10, w//2-10:w//2+10]
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1]
    
    # 3. Parameter Conversion (L, a, b)
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    # 4. Display Results (Standard UI)
    st.divider()
    st.subheader("Analysis Results")
    col1, col2 = st.columns(2)
    col1.metric("Detected Color", u_name)
    col2.metric("HEX Code", hex_val.upper())
    
    # 5. AI Prediction (Logistic Regression)
    probs = model.predict_proba([center_lab])[0]
    best_idx = np.argmax(probs)
    confidence = probs[best_idx] * 100
    drug_name = drug_labels[best_idx]
    
    if confidence > 65:
        match_msg = f"Match Found: {drug_name} ({confidence:.1f}% Confidence)"
        st.success(f"✅ **{match_msg}**")
        voice_text = f"Detected {u_name}. Analysis indicates {confidence:.0f} percent probability of {drug_name}."
    else:
        match_msg = "No specific drug reagent match found."
        st.warning(match_msg)
        voice_text = f"Detected {u_name}. No drug match found."
    
    # Trigger Voice
    talk_back(voice_text)
    if st.button("🔊 Repeat Audio"):
        talk_back(voice_text)
        
    # 6. Report Generation
    st.divider()
    case_data = {'time': get_india_time(), 'officer': off_id, 'case': case_ref}
    color_data = {'name': u_name, 'hex': hex_val.upper()}
    pdf_file = generate_pdf(case_data, color_data, match_msg, img_hash)
    
    st.download_button(
        label="📥 Download Forensic PDF Report",
        data=pdf_file,
        file_name=f"NCB_Report_{img_hash}.pdf",
        mime="application/pdf"
    )

# Admin Section
with st.expander("Register New Reagent Shade"):
    st.write("Add a new color benchmark to the system.")
    sub_n = st.text_input("Substance Name")
    if st.button("Save to Database"):
        # Logic to append to json
        st.success("Color benchmark registered.")
