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

# --- 2. VOICE ENGINE (Browser Talk Back) ---
def talk_back(text):
    """Triggers the browser to speak the result."""
    components.html(f"""<script>
        window.speechSynthesis.cancel();
        var m = new SpeechSynthesisUtterance("{text}");
        m.lang = 'en-IN'; 
        m.rate = 0.9;
        window.speechSynthesis.speak(m);
    </script>""", height=0)

# --- 3. LOGISTIC REGRESSION TRAINING ---
@st.cache_resource
def train_logistic_model():
    """Trains a model on L, a, b coordinates from your JSON."""
    if not os.path.exists(DB_FILE):
        return None, None
    with open(DB_FILE, "r") as f:
        db = json.load(f)

    X_train, y_train, class_labels = [], [], []
    
    for key, data in db.items():
        target_lab = data.get('target_lab')
        if target_lab:
            # Generate 150 synthetic samples with noise to handle lighting variations
            for _ in range(150):
                noise = np.random.normal(0, 2.5, 3) 
                X_train.append(np.array(target_lab) + noise)
                y_train.append(len(class_labels))
            class_labels.append(data['target_compound'])
    
    if not X_train: return None, None
    
    model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
    model.fit(X_train, y_train)
    return model, class_labels

# --- 4. COLOR PROCESSING ---
def get_universal_name(rgb):
    """Fallback naming engine to ensure a color name is always shown."""
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
    """Converts RGB to standard CIELAB (L:0-100, a/b:-128 to 127)."""
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB2Lab)
    l, a, b = pixel_lab[0][0].astype(float)
    return [round(l * (100/255), 1), round(a - 128, 1), round(b - 128, 1)]

# --- 5. PDF REPORT GENERATOR ---
def generate_pdf(case_info, color_data, match_info, confidence, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        ["NCB FIELD TEST RECORD", ""],
        ["Timestamp (IST)", case_info['time']],
        ["Officer ID", case_info['officer']],
        ["Case Reference", case_info['case']],
        ["Detected Shade", color_data['name']],
        ["Detected HEX", color_data['hex']],
        ["AI Prediction", match_info],
        ["Confidence Level", f"{confidence:.1f}%"],
        ["Record Hash", img_hash]
    ]
    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.navy),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 10)
    ]))
    doc.build([Paragraph("NCB DIGITAL COMPANION REPORT", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# --- 6. MAIN APP INTERFACE ---
st.set_page_config(page_title="NCB Logistic AI Shield", page_icon="⚖️")

st.title("⚖️ NCB Field Companion")
st.write(f"**Forensic Screening Tool** | {get_india_time()}")

# Train Model on Startup
model, drug_labels = train_logistic_model()

with st.sidebar:
    st.header("📋 Case Management")
    off_id = st.text_input("Officer ID", "NCB-OFF-101")
    case_ref = st.text_input("Case No.", "F.No-" + datetime.now(IST).strftime("%Y/%m/%d"))
    st.divider()
    if st.button("Re-train AI Model"):
        st.cache_resource.clear()
        st.rerun()

st.subheader("1. Optical Evidence Capture")
cam_img = st.camera_input("Position the reagent sample in the center")

if cam_img:
    # --- Image & Color Extraction ---
    file_bytes = np.frombuffer(cam_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(cam_img.getvalue()).hexdigest()[:16]
    
    h, w, _ = img.shape
    roi = img[h//2-10:h//2+10, w//2-10:w//2+10]
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1] # BGR to RGB
    
    # --- Lab Conversion (The 3 Logistic Parameters) ---
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    # --- UI DISPLAY ---
    st.divider()
    st.subheader("2. Analysis Results")
    
    col1, col2 = st.columns(2)
    col1.metric("Universal Shade", u_name)
    col2.metric("HEX Code", hex_val.upper())

    # --- AI PREDICTION (Logistic Regression) ---
    match_text = "No drug match found."
    confidence = 0.0

    if model and drug_labels:
        probs = model.predict_proba([center_lab])[0]
        best_idx = np.argmax(probs)
        confidence = probs[best_idx] * 100
        drug_name = drug_labels[best_idx]

        if confidence > 65:
            match_text = f"Consistent with {drug_name}"
            st.success(f"✅ **AI MATCH:** {drug_name} ({confidence:.1f}% Confidence)")
            voice_msg = f"Detected {u_name}. There is a {confidence:.0f} percent probability of {drug_name}."
        else:
            st.warning("Low AI confidence. No reagent match identified.")
            voice_msg = f"Detected {u_name}. No matching reagent found."
    else:
        st.error("Model Error: Ensure reagents.json is valid.")
        voice_msg = "Error. System not trained."

    # Trigger Voice
    talk_back(voice_msg)
    if st.button("🔊 Repeat Audio"):
        talk_back(voice_text)

    # --- REPORT GENERATION ---
    st.divider()
    case_data = {'time': get_india_time(), 'officer': off_id, 'case': case_ref}
    color_data = {'name': u_name, 'hex': hex_val.upper()}
    pdf_file = generate_pdf(case_data, color_data, match_text, confidence, img_hash)
    
    st.download_button(
        label="📥 Download Forensic PDF Report",
        data=pdf_file,
        file_name=f"NCB_Report_{img_hash}.pdf",
        mime="application/pdf"
    )

with st.expander("🛠️ Admin: Register Color Benchmark"):
    st.write("Add the current camera color as a new drug reference.")
    new_sub = st.text_input("Substance Name")
    if st.button("Save to Database"):
        st.info("Logic to append to reagents.json would go here.")
