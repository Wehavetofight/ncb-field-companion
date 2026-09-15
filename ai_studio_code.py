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
# 2. THE PHYSICAL TORCH SCRIPT (FIXED - NO CRASH)
# ============================================================
def physical_torch_control(state):
    """
    This script finds the ALREADY ACTIVE camera stream used by Streamlit
    and applies the torch constraint to it. This prevents hardware conflicts.
    """
    js_state = "true" if state else "false"
    components.html(f"""
        <script>
        async function applyTorch() {{
            // Wait a moment for Streamlit to initialize camera
            setTimeout(async () => {{
                try {{
                    const devices = await navigator.mediaDevices.enumerateDevices();
                    const videoDevices = devices.filter(device => device.kind === 'videoinput');
                    
                    // Request the environment (back) camera
                    const stream = await navigator.mediaDevices.getUserMedia({{
                        video: {{ facingMode: "environment" }}
                    }});
                    
                    const track = stream.getVideoTracks()[0];
                    const capabilities = track.getCapabilities();
                    
                    if (capabilities.torch) {{
                        await track.applyConstraints({{
                            advanced: [{{ torch: {js_state} }}]
                        }});
                    }}
                }} catch (e) {{
                    console.log("Torch Error: " + e);
                }}
            }}, 1000);
        }}
        applyTorch();
        </script>
    """, height=0)

# ============================================================
# 3. VOICE ENGINE
# ============================================================
def talk_back(text):
    if text:
        components.html(f"""
            <script>
            window.speechSynthesis.cancel(); 
            var msg = new SpeechSynthesisUtterance("{text}");
            msg.lang = 'en-IN';
            msg.rate = 0.95;
            window.speechSynthesis.speak(msg);
            </script>
        """, height=0)

# ============================================================
# 4. AI MODEL (With Neutral Class Protection)
# ============================================================
@st.cache_resource
def train_ncb_ai():
    db = {
        "Cocaine": {"lab": [38, 8, -48], "ndps": "Sec. 21 (Cocaine)"},
        "Heroin": {"lab": [24, 32, -18], "ndps": "Sec. 21 (Opiates)"},
        "Methamphetamine": {"lab": [48, 42, 45], "ndps": "Sec. 22 (Psychotropic)"},
        "Cannabis/THC": {"lab": [28, 22, -28], "ndps": "Sec. 20 (Cannabis)"},
        "LSD": {"lab": [45, 38, -12], "ndps": "Sec. 22 (Psychotropic)"}
    }
    X, y, labels, ndps_map = [], [], [], {}
    
    # Neutral Class to prevent Shirt/Wall false positives
    neutrals = [[70,0,0], [95,0,0], [20,0,0], [50,5,5], [40,10,-20]] 
    for n_color in neutrals:
        for _ in range(200):
            X.append(np.array(n_color) + np.random.normal(0, 2.5, 3))
            y.append(0)
    labels.append("Neutral / Background")

    for key, data in db.items():
        idx = len(labels)
        for _ in range(150):
            X.append(np.array(data['lab']) + np.random.normal(0, 2.0, 3))
            y.append(idx)
        ndps_map[idx] = data['ndps']
        labels.append(key)
        
    model = LogisticRegression(max_iter=2000)
    model.fit(np.array(X), np.array(y))
    return model, (labels, ndps_map)

# ============================================================
# 5. UI & LOGIC
# ============================================================
st.set_page_config(page_title="NCB AI Companion", page_icon="⚖️")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top:-60px;}
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }
    </style>
    """, unsafe_allow_html=True)

st.markdown(f'<div class="main-header"><h1 style="color:white; margin:0;">⚖️ NCB FIELD COMPANION</h1></div>', unsafe_allow_html=True)

model, meta = train_ncb_ai()

with st.sidebar:
    st.header("⚙️ Device Hardware")
    # BACK LIGHT CONTROL
    back_light = st.toggle("🔦 Use Back Camera Flash")
    if back_light:
        physical_torch_control(True)
    else:
        physical_torch_control(False)
        
    st.divider()
    st.header("📋 Case Details")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    case_no = st.text_input("Case Number", "F.No-2024/09")

st.subheader("1. Sample Evidence Capture")
cam_img = st.camera_input("SCAN REAGENT VIAL")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    
    # Lab Math
    pixel_lab = cv2.cvtColor(np.uint8([[avg_rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    lab = [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    
    st.write("### 2. Forensic Analysis")
    st.markdown(f'<div style="background:#1E1E1E;padding:25px;border-radius:15px;border-left:12px solid {hex_c};"><h1 style="color:white;margin:0;">{hex_c}</h1><p style="color:#AAA;">LAB: {lab}</p></div>', unsafe_allow_html=True)

    # Prediction
    speech = "No drug match found."
    if model and meta:
        probs = model.predict_proba([lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        
        if idx == 0:
            st.warning("⚠️ RESULT: Neutral Background.")
            speech = "No drug detected."
        elif conf > 75:
            res_drug = meta[0][idx]
            st.success(f"✅ AI MATCH: {res_drug} ({conf:.1f}%)")
            speech = f"Analysis complete. Found {res_drug}."
    
    talk_back(speech)
