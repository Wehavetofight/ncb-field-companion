import streamlit as st
import cv2
import numpy as np
import json
import os
from sklearn.ensemble import RandomForestClassifier # Switched to Random Forest
import streamlit.components.v1 as components

# --- AI MODEL TRAINING (RANDOM FOREST) ---
@st.cache_resource
def train_ai_model():
    if not os.path.exists("reagents.json"):
        return None, None
    with open("reagents.json", "r") as f:
        db = json.load(f)

    X, y, labels = [], [], []
    for key, data in db.items():
        target_lab = data.get('target_lab')
        if target_lab:
            # Generate 150 synthetic samples with noise to make the model robust
            for _ in range(150):
                noise = np.random.normal(0, 3.0, 3) 
                X.append(np.array(target_lab) + noise)
                y.append(len(labels))
            labels.append(data['target_compound'])
    
    if not X: return None, None
    
    # Random Forest is better for "noisy" camera data
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    return model, labels

# --- TALK BACK ---
def talk_back(text):
    components.html(f"""<script>
        window.speechSynthesis.cancel();
        var m = new SpeechSynthesisUtterance("{text}");
        m.lang = 'en-IN'; window.speechSynthesis.speak(m);
    </script>""", height=0)

# --- APP UI ---
st.set_page_config(page_title="NCB AI Companion", layout="centered")

# Professional App Look
st.markdown("""<style>
    .stApp {background-color: #0E1117;}
    .stButton>button {width:100%; border-radius:15px; height:3.5em; background:#002F6C; color:white; font-weight:bold; border:1px solid #4E9F3D;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
</style>""", unsafe_allow_html=True)

st.title("⚖️ NCB AI Shield")
st.caption("Random Forest Forensic Classifier")

model, drug_labels = train_ai_model()

cam_in = st.camera_input("CAPTURE SAMPLE")

if cam_in and model:
    # 1. Color Extraction
    img = cv2.imdecode(np.frombuffer(cam_in.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    h, w, _ = img.shape
    roi = img[h//2-10:h//2+10, w//2-10:w//2+10]
    rgb = np.mean(roi, axis=(0,1))[::-1]
    
    # 2. Convert to Lab (Scientific Scale)
    pix = np.uint8([[rgb]])
    lab = cv2.cvtColor(pix, cv2.COLOR_RGB2Lab)[0][0].astype(float)
    standard_lab = [lab[0]*(100/255), lab[1]-128, lab[2]-128]
    
    # 3. Random Forest Prediction
    probs = model.predict_proba([standard_lab])[0]
    best_idx = np.argmax(probs)
    conf = probs[best_idx] * 100
    drug_name = drug_labels[best_idx]

    # 4. Results UI
    hex_c = '#%02x%02x%02x' % (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    st.markdown(f"""<div style="background:#1E1E1E; padding:20px; border-radius:15px; border-left:10px solid {hex_c};">
        <h2 style="color:white; margin:0;">Detected Color</h2>
        <p style="color:#4E9F3D; font-weight:bold; font-size:1.2em;">AI Confidence: {conf:.1f}%</p>
    </div>""", unsafe_allow_html=True)

    if conf > 70:
        res_msg = f"Match found: {drug_name}"
        st.success(f"✅ **{res_msg}**")
        talk_back(f"Analysis complete. {conf:.0f} percent confidence of {drug_name}")
    else:
        res_msg = "No drug match found."
        st.warning(res_msg)
        talk_back("No matching drug found in database.")

    if st.button("🔊 REPEAT ANNOUNCEMENT"):
        talk_back(f"Confidence {conf:.0f} percent for {drug_name}")
