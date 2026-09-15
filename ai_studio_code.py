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
import streamlit.components.v1 as components

# Machine Learning Imports
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import NotFittedError

# PDF Libraries
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# --- CONFIGURATION ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# --- TALK BACK ---
def talk_back(text):
    components.html(f"""
        <script>
        window.speechSynthesis.cancel(); 
        var msg = new SpeechSynthesisUtterance("{text}");
        msg.lang = 'en-IN';
        window.speechSynthesis.speak(msg);
        </script>
    """, height=0)

# --- ML MODEL TRAINING ---
@st.cache_resource
def train_logistic_model():
    """Trains a Logistic Regression model using data from reagents.json."""
    if not os.path.exists(DB_FILE):
        return None, None

    with open(DB_FILE, "r") as f:
        db = json.load(f)

    X_train = []
    y_train = []
    class_names = []

    for key, data in db.items():
        target_lab = data.get('target_lab')
        if target_lab:
            # Generate 100 synthetic samples with 'noise' to simulate different lighting
            for _ in range(100):
                noise = np.random.normal(0, 2.5, 3) # Add small random variations
                sample = np.array(target_lab) + noise
                X_train.append(sample)
                y_train.append(len(class_names))
            class_names.append(data['target_compound'])

    if len(X_train) == 0:
        return None, None

    model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
    model.fit(np.array(X_train), np.array(y_train))
    return model, class_names

# --- COLOR ENGINES ---
def get_universal_name(rgb):
    try:
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        min_dist = float('inf')
        closest_name = "Custom Shade"
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

# --- APP UI ---
st.set_page_config(page_title="NCB AI Shield", page_icon="⚖️")
st.title("⚖️ NCB AI Field Companion")
st.caption(f"Machine Learning Powered Screening | {get_india_time()}")

# Train Model on Startup
ml_model, drug_labels = train_logistic_model()

with st.sidebar:
    st.header("📋 Administration")
    off_id = st.text_input("Officer ID", "NCB-DEL-442")
    case_ref = st.text_input("Case No.", "F.No-" + datetime.now(IST).strftime("%Y/%m/%d"))
    if st.button("Re-train ML Model"):
        st.cache_resource.clear()
        st.rerun()

st.subheader("1. Evidence Capture")
camera_img = st.camera_input("Scan Reagent Vial")

if camera_img:
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    
    # Process color
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1]
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    # UI Display
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:20px; border-radius:15px; border-left:12px solid {hex_val};">
            <h1 style="margin:0; color:white;">{u_name}</h1>
            <p style="margin:0; color:#AAA;">HEX: {hex_val.upper()} | LAB: {center_lab}</p>
        </div>
    """, unsafe_allow_html=True)

    # --- LOGISTIC REGRESSION PREDICTION ---
    st.write("### 2. AI Logistic Regression Prediction")
    
    if ml_model and drug_labels:
        # Get probability from ML model
        probs = ml_model.predict_proba([center_lab])[0]
        max_idx = np.argmax(probs)
        confidence = probs[max_idx] * 100
        predicted_drug = drug_labels[max_idx]
        
        if confidence > 65: # Confidence threshold
            st.success(f"🤖 **ML PREDICTION:** {predicted_drug}")
            st.progress(confidence / 100)
            st.write(f"Model Confidence: **{confidence:.1f}%**")
            
            speech = f"Attention. Machine learning indicates {confidence:.0f} percent probability of {predicted_drug}."
            talk_back(speech)
        else:
            st.warning("Low ML confidence. No definitive drug match found.")
            talk_back(f"Detected shade is {u_name}. No drug match found.")
    else:
        st.error("ML Model not trained. Please add reagents to JSON.")

    st.write("---")
    # PDF and Admin Logic remains the same...
