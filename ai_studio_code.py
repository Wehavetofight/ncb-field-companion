import streamlit as st
import cv2
import numpy as np
import json
import os
import pytz
from sklearn.linear_model import LogisticRegression # Clean & Professional
import streamlit.components.v1 as components

# --- 1. AI TRAINING (LOGISTIC REGRESSION) ---
@st.cache_resource
def train_ncb_model():
    if not os.path.exists("reagents.json"):
        return None, None
    with open("reagents.json", "r") as f:
        db = json.load(f)

    X, y, labels = [], [], []
    for key, data in db.items():
        target_lab = data.get('target_lab')
        if target_lab:
            # We generate synthetic variations to teach the model about lighting
            for _ in range(120):
                noise = np.random.normal(0, 2.0, 3) 
                X.append(np.array(target_lab) + noise)
                y.append(len(labels))
            labels.append(data['target_compound'])
    
    if not X: return None, None
    
    # Logistic Regression is very stable for 3-feature (L,a,b) data
    model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
    model.fit(X, y)
    return model, labels

# --- 2. VOICE ENGINE ---
def talk_back(text):
    components.html(f"""<script>
        window.speechSynthesis.cancel();
        var m = new SpeechSynthesisUtterance("{text}");
        m.lang = 'en-IN'; window.speechSynthesis.speak(m);
    </script>""", height=0)

# --- 3. APP INTERFACE ---
st.set_page_config(page_title="NCB Logistic AI", layout="centered")

st.markdown("""<style>
    .stApp {background-color: #0E1117;}
    .stButton>button {width:100%; border-radius:12px; height:3.5em; background:#002F6C; color:white; font-weight:bold; border:1px solid #4E9F3D;}
    header {visibility: hidden;} footer {visibility: hidden;}
</style>""", unsafe_allow_html=True)

st.title("⚖️ NCB Logistic AI Shield")
st.caption("Forensic Color Classification Model")

model, drug_labels = train_ncb_model()

cam_in = st.camera_input("SCAN REAGENT")

if cam_in and model:
    # Get the image and extract center color
    img = cv2.imdecode(np.frombuffer(cam_in.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    h, w, _ = img.shape
    roi = img[h//2-10:h//2+10, w//2-10:w//2+10]
    rgb = np.mean(roi, axis=(0,1))[::-1]
    
    # Convert to CIELAB (The 3 Parameters)
    pix = np.uint8([[rgb]])
    lab = cv2.cvtColor(pix, cv2.COLOR_RGB2Lab)[0][0].astype(float)
    standard_lab = [lab[0]*(100/255), lab[1]-128, lab[2]-128] # Scaled parameters
    
    # ML PREDICTION
    probs = model.predict_proba([standard_lab])[0]
    best_idx = np.argmax(probs)
    confidence = probs[best_idx] * 100
    drug_name = drug_labels[best_idx]

    # UI DISPLAY
    hex_c = '#%02x%02x%02x' % (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:20px; border-radius:15px; border-left:10px solid {hex_c};">
            <h3 style="color:white; margin:0;">AI Analysis Result</h3>
            <p style="color:#4E9F3D; font-size:1.5em; font-weight:bold; margin:0;">{confidence:.1f}% Confidence</p>
        </div>
    """, unsafe_allow_html=True)

    if confidence > 65:
        st.success(f"🔍 **PREDICTED SUBSTANCE:** {drug_name}")
        speech = f"Analysis complete. Found {confidence:.0f} percent probability of {drug_name}."
    else:
        st.warning("⚠️ Low AI confidence. No reagent match found.")
        speech = "Warning. Low confidence result. No drug match found."
    
    talk_back(speech)

    if st.button("🔊 REPEAT ANNOUNCEMENT"):
        talk_back(speech)
