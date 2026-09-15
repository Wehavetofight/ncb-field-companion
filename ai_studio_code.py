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

# --- CONFIGURATION ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')
NCB_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Narcotics_Control_Bureau_logo.png/220px-Narcotics_Control_Bureau_logo.png"

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

def talk_back(text):
    components.html(f"""<script>window.speechSynthesis.cancel(); var msg = new SpeechSynthesisUtterance("{text}"); msg.lang = 'en-IN'; msg.rate = 0.9; window.speechSynthesis.speak(msg);</script>""", height=0)

# --- 1. DATABASE LOADER (The "Datasets" Part) ---
@st.cache_resource
def load_and_train_db():
    if not os.path.exists(DB_FILE):
        return None, None
    with open(DB_FILE, "r") as f:
        db = json.load(f)
    
    X, y, labels, metadata = [], [], [], []
    for key, val in db.items():
        # Using LAB coordinates from your UNODC/DanceSafe dataset
        for _ in range(120): # Augmented training data
            noise = np.random.normal(0, 2.0, 3)
            X.append(np.array(val['target_lab']) + noise)
            y.append(len(labels))
        labels.append(val['target_compound'])
        metadata.append(val)
    
    model = LogisticRegression(multi_class='multinomial', max_iter=1000)
    model.fit(X, y)
    return model, (labels, metadata)

# --- 2. COLOR FORENSICS ---
def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

def get_universal_name(rgb):
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 12: return "Neutral Gray/Charcoal"
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
    except: return "Detected Shade"

# --- 3. APP UI ---
st.set_page_config(page_title="NCB Field Companion", page_icon="⚖️")
st.markdown("""<style>.stApp { background-color: #0E1117; } .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top:-60px; } .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }</style>""", unsafe_allow_html=True)

st.markdown(f'<div class="main-header"><img src="{NCB_LOGO}" width="70"><h1 style="color:white; margin:0;">NCB FIELD COMPANION</h1></div>', unsafe_allow_html=True)
st.caption(f"SIH 2024 | Forensic Digital Evidence Support | {get_india_time()}")

# Load AI and Database
model, meta = load_and_train_db()
db_data = meta[1] if meta else []
kit_list = sorted(list(set([v['reagent'] for v in db_data]))) if db_data else ["Marquis", "Scott", "Ehrlich"]

with st.sidebar:
    st.header("📋 Forensic Protocol")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    active_kit = st.selectbox("Select Field Kit in Use", kit_list)
    st.info(f"AI calibrated for {active_kit} kit reactions.")
    if st.button("🔄 Sync Official Dataset"):
        st.cache_resource.clear()
        st.rerun()

st.subheader(f"1. Capture {active_kit} Reagent Frame")
cam_img = st.camera_input("Place vial in the center circle")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    
    # Analyze center color
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    lab = rgb_to_lab_scaled(avg_rgb)
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    u_name = get_universal_name(avg_rgb)
    
    # UI Display
    st.write("### 2. Forensic Result")
    st.markdown(f"""<div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_c};"><h1 style="margin:0; color:white;">{u_name}</h1><p style="margin:0; color:#AAA;"><b>HEX:</b> {hex_c.upper()} | <b>CIELAB:</b> {lab}</p></div>""", unsafe_allow_html=True)

    # AI Prediction Filtered by Kit
    res_drug, conf, ndps = "No Match", 0.0, "N/A"
    if model:
        probs = model.predict_proba([lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        predicted_kit_info = db_data[idx]
        
        # KEY: Verify that the AI result matches the kit the officer is actually using
        if predicted_kit_info['reagent'] == active_kit and conf > 65:
            res_drug = predicted_kit_info['target_compound']
            ndps = predicted_kit_info['ndps_section']
            st.success(f"⚖️ **POSS. MATCH:** {res_drug} ({conf:.1f}% Confidence)")
            st.info(f"📜 **Legal Provision:** {ndps}")
            speech = f"Analysis complete. Found {conf:.0f} percent probability of {res_drug}."
        else:
            st.warning(f"No high-confidence match for {active_kit} kit expected colors.")
            speech = f"Detected {u_name}. No drug match found."
    
    talk_back(speech)
    st.write("---")
    # PDF Report button would go here...
