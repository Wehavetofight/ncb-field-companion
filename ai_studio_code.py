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

# PDF Forensic Libraries
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# ============================================================
# 1. CORE CONFIGURATION
# ============================================================
IST = pytz.timezone('Asia/Kolkata')
NCB_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Narcotics_Control_Bureau_logo.png/220px-Narcotics_Control_Bureau_logo.png"

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# ============================================================
# 2. THE FLASH/TORCH CONTROL (JavaScript)
# ============================================================
def torch_control(state):
    # This script tries to find the camera track and toggle the 'torch' capability
    val = "true" if state else "false"
    components.html(f"""
        <script>
        async function toggleFlash() {{
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ video: {{ facingMode: "environment" }} }});
                const track = stream.getVideoTracks()[0];
                const capabilities = track.getCapabilities();
                if (capabilities.torch) {{
                    await track.applyConstraints({{ advanced: [{{ torch: {val} }}] }});
                }}
            }} catch (e) {{ console.log("Flash not accessible"); }}
        }}
        toggleFlash();
        </script>
    """, height=0)

# ============================================================
# 3. AI MODEL (Enhanced with better Neutral detection)
# ============================================================
@st.cache_resource
def train_ncb_ai():
    db = {
        "Cocaine": {"target_lab": [38, 8, -48], "ndps": "Sec. 21 (Cocaine)"},
        "Heroin": {"target_lab": [24, 32, -18], "ndps": "Sec. 21 (Opiates)"},
        "Methamphetamine": {"target_lab": [48, 42, 45], "ndps": "Sec. 22 (Psychotropic)"},
        "Cannabis/THC": {"target_lab": [28, 22, -28], "ndps": "Sec. 20 (Cannabis)"},
        "LSD": {"target_lab": [45, 38, -12], "ndps": "Sec. 22 (Psychotropic)"}
    }
    X, y, labels, ndps_map = [], [], [], {}
    
    # NEUTRAL CLASS (Class 0) - Heavily weighted to prevent Shirt/Wall matches
    # We add common "non-drug" colors: White, Gray, Black, Beige (Skin), Blue (Jeans)
    neutrals = [[70,0,0], [95,0,0], [20,0,0], [50,5,5], [40,10,-20]] 
    for n_color in neutrals:
        for _ in range(200): # More samples for the neutral class
            X.append(np.array(n_color) + np.random.normal(0, 2.5, 3))
            y.append(0)
    labels.append("Neutral / Background")

    for key, data in db.items():
        idx = len(labels)
        for _ in range(150):
            X.append(np.array(data['target_lab']) + np.random.normal(0, 2.0, 3))
            y.append(idx)
        ndps_map[idx] = data['ndps']
        labels.append(key)
        
    model = LogisticRegression(max_iter=2000)
    model.fit(np.array(X), np.array(y))
    return model, (labels, ndps_map)

# ============================================================
# 4. COLOR NAMING ENGINE
# ============================================================
def get_universal_name(rgb):
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 15: return "Neutral Gray"
    
    forensic_colors = {
        "Crimson Red": (153, 0, 0), "Deep Maroon": (80, 0, 0), "Blood Orange": (255, 69, 0),
        "Amber": (255, 191, 0), "Forest Green": (34, 139, 34), "Cobalt Blue": (0, 71, 171),
        "Midnight Blue": (25, 25, 112), "Deep Purple": (48, 25, 52), "Violet": (138, 43, 226)
    }
    best_name, min_dist = "Custom Color", float('inf')
    for name, c_rgb in forensic_colors.items():
        dist = np.sqrt((c_rgb[0]-r)**2 + (c_rgb[1]-g)**2 + (c_rgb[2]-b)**2)
        if dist < min_dist: min_dist = dist; best_name = name
    return best_name

def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

# ============================================================
# 5. APP UI
# ============================================================
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top:-60px;}
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }
    </style>
    """, unsafe_allow_html=True)

st.markdown(f'<div class="main-header"><h1 style="color:white; margin:0;">⚖️ NCB FIELD COMPANION</h1><p style="color:#4E9F3D; margin:0; font-weight:bold;">Forensic Intelligence Unit</p></div>', unsafe_allow_html=True)

model, meta = train_ncb_ai()

with st.sidebar:
    st.header("⚙️ Device Controls")
    # THE FLASH OPTION
    flash_on = st.toggle("🔦 Flashlight (Torch)")
    if flash_on:
        torch_control(True)
    else:
        torch_control(False)
        
    st.divider()
    st.header("📋 Case Administration")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    case_no = st.text_input("Case Reference", "F.No-2024/09")

st.subheader("1. Sample Evidence Capture")
cam_img = st.camera_input("SCAN REAGENT VIAL")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    
    # Process Center Area
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    lab = rgb_to_lab_scaled(avg_rgb)
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    u_name = get_universal_name(avg_rgb)
    
    st.write("### 2. Forensic Analysis")
    st.markdown(f'<div style="background:#1E1E1E;padding:25px;border-radius:15px;border-left:12px solid {hex_c};"><h1 style="margin:0; color:white;">{u_name}</h1><p style="margin:0; color:#AAA;">HEX: {hex_c.upper()} | LAB: {lab}</p></div>', unsafe_allow_html=True)

    # Prediction
    if model and meta:
        probs = model.predict_proba([lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        
        if idx == 0: # This is the neutral class (Shirt/Wall fix)
            st.warning("⚠️ RESULT: No drug reagent detected (Background Neutral).")
            speech = "No drug detected in the sample."
        elif conf > 75:
            res_drug = meta[0][idx]
            st.success(f"✅ AI MATCH: {res_drug} ({conf:.1f}% Confidence)")
            st.info(f"📜 Statute: {meta[1][idx]}")
            speech = f"Analysis complete. Probability of {res_drug} is {conf:.0f} percent."
        else:
            st.warning("Inconclusive result. Low AI confidence.")
            speech = "Result is inconclusive."
    
    # Talk Back
    components.html(f'<script>window.speechSynthesis.cancel(); var m = new SpeechSynthesisUtterance("{speech}"); m.lang="en-IN"; window.speechSynthesis.speak(m);</script>', height=0)

    if st.button("🔊 Repeat Audio"):
        components.html(f'<script>window.speechSynthesis.cancel(); var m = new SpeechSynthesisUtterance("{speech}"); m.lang="en-IN"; window.speechSynthesis.speak(m);</script>', height=0)
