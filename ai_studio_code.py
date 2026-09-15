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

# --- 1. CONFIGURATION ---
DB_FILE = "reagents.json"
CSV_FILE = "drug_reagents.csv"
IST = pytz.timezone('Asia/Kolkata')
NCB_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Narcotics_Control_Bureau_logo.png/220px-Narcotics_Control_Bureau_logo.png"

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# --- 2. DATASET & AI TRAINING (With Safeguards) ---
@st.cache_resource
def train_ncb_ai():
    # Load from reagents.json (created from your CSV)
    if not os.path.exists(DB_FILE): return None, None
    try:
        with open(DB_FILE, "r") as f: db = json.load(f)
        X, y, labels, kit_map = [], [], [], {}
        
        # Add a "Neutral" class to the AI to prevent False Positives
        # This teaches the AI what 'Normal objects' look like
        neutral_colors = [[60,0,0], [20,0,0], [90,0,0]] # Grays/Whites/Blacks
        for nc in neutral_colors:
            for _ in range(50):
                X.append(np.array(nc) + np.random.normal(0, 2, 3))
                y.append(0)
        labels.append("Neutral/No Drug")

        for key, data in db.items():
            t_lab = data.get('target_lab')
            if t_lab:
                class_idx = len(labels)
                for _ in range(150):
                    noise = np.random.normal(0, 2.0, 3) 
                    X.append(np.array(t_lab) + noise)
                    y.append(class_idx)
                labels.append(data['target_compound'])
                kit_map[class_idx] = data['reagent']
        
        model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
        model.fit(np.array(X), np.array(y))
        return model, (labels, kit_map)
    except: return None, None

# --- 3. UI & LOGIC ---
st.set_page_config(page_title="NCB AI Shield", page_icon="⚖️")

# Professional Header
st.markdown(f'<div style="background:#002F6C;padding:15px;border-radius:10px;text-align:center;border-bottom:4px solid #4E9F3D;"><img src="{NCB_LOGO}" width="60"><h2 style="color:white;margin:0;">NCB FIELD COMPANION</h2></div>', unsafe_allow_html=True)

model, meta = train_ncb_ai()

with st.sidebar:
    st.header("🛡️ Forensic Protocol")
    # SAFEGUARD 1: Officer must select the kit they are using
    all_kits = ["Marquis", "Scott", "Ehrlich", "Duquenois", "Mandelin", "Mecke"]
    selected_kit = st.selectbox("Select Active Reagent Kit", all_kits)
    st.warning(f"AI will only report matches valid for the {selected_kit} kit.")
    st.divider()
    off_id = st.text_input("Officer ID", "NCB-DEL-442")

cam_img = st.camera_input("SCAN TEST VIAL")

if cam_img and model:
    img = cv2.imdecode(np.frombuffer(cam_img.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    roi = img[img.shape[0]//2-15:img.shape[0]//2+15, img.shape[1]//2-15:img.shape[1]//2+15]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    
    # Lab Conversion
    pixel_lab = cv2.cvtColor(np.uint8([[avg_rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    lab = [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))

    # AI Prediction
    probs = model.predict_proba([lab])[0]
    idx = np.argmax(probs)
    confidence = probs[idx] * 100
    drug_name = meta[0][idx]
    required_kit = meta[1].get(idx, "None")

    # SAFEGUARD 2: Kit Validation Logic
    # The AI found a match, but is it the kit the officer is actually using?
    is_valid_match = (required_kit == selected_kit) and (confidence > 75)

    st.write("### Analysis Result")
    st.markdown(f'<div style="background:#1E1E1E;padding:20px;border-radius:10px;border-left:10px solid {hex_c};"><h1 style="color:white;margin:0;">{hex_c}</h1><p style="color:#AAA;">Lab: {lab}</p></div>', unsafe_allow_html=True)

    if is_valid_match:
        st.success(f"✅ **CONFIRMED MATCH:** {drug_name}")
        st.metric("AI Confidence", f"{confidence:.1f}%")
        msg = f"Match found. Consistent with {drug_name} using {selected_kit} reagent."
    else:
        # If it's blue but not the right kit, it's a "Neutral" result
        st.error("❌ **NO FORENSIC MATCH**")
        st.info(f"The detected color does not match the standard protocol for a {selected_kit} test.")
        msg = f"No match found for {selected_kit} reagent."

    # Talk Back
    components.html(f'<script>window.speechSynthesis.cancel(); var m = new SpeechSynthesisUtterance("{msg}"); m.lang="en-IN"; window.speechSynthesis.speak(m);</script>', height=0)
