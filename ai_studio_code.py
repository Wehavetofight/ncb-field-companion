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

# --- 1. CONFIGURATION ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# --- 2. HARDWARE & SECURITY CONTROLS (JAVASCRIPT) ---
def inject_hardware_controls(torch_on):
    """
    1. Controls the Flashlight (Torch) via Web Hardware API.
    2. Monitors app switching (Visibility API) to shut down camera.
    """
    torch_js = "true" if torch_on else "false"
    
    components.html(f"""
        <script>
        // 1. FLASHLIGHT CONTROL
        async function toggleTorch(state) {{
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ video: {{ facingMode: "environment" }} }});
                const track = stream.getVideoTracks()[0];
                const capabilities = track.getCapabilities();
                if (capabilities.torch) {{
                    await track.applyConstraints({{ advanced: [{{ torch: state }}] }});
                }}
            }} catch (e) {{ console.log("Flashlight not supported or permission denied"); }}
        }}
        
        // Apply torch state
        toggleTorch({torch_js});

        // 2. APP SWITCH AUTO-SHUTDOWN
        document.addEventListener("visibilitychange", () => {{
            if (document.visibilityState === 'hidden') {{
                // Force stop all camera streams if user switches apps
                navigator.mediaDevices.getUserMedia({{video: true}}).then(stream => {{
                    stream.getTracks().forEach(track => track.stop());
                }});
                window.location.reload(); // Refresh to ensure clean state
            }}
        }});
        </script>
    """, height=0)

# --- 3. AI MODEL TRAINING ---
@st.cache_resource
def train_ncb_ai():
    db = {
        "Cocaine": {"target_compound": "Cocaine (Scott Reagent)", "target_lab": [38.0, 8.0, -48.0], "ndps": "Sec. 21"},
        "Heroin": {"target_compound": "Heroin (Marquis Reagent)", "target_lab": [24.0, 32.0, -18.0], "ndps": "Sec. 21"},
        "Meth": {"target_compound": "Methamphetamine (Marquis)", "target_lab": [48.0, 42.0, 45.0], "ndps": "Sec. 22"},
        "Cannabis": {"target_compound": "Cannabis (Duquenois)", "target_lab": [28.0, 22.0, -28.0], "ndps": "Sec. 20"},
        "Neutral": {"target_compound": "No Match / Negative", "target_lab": [70.0, 0.0, 0.0], "ndps": "N/A"}
    }
    try:
        X, y, labels, ndps_map = [], [], [], {}
        for key, data in db.items():
            t_lab = data.get('target_lab')
            class_idx = len(labels)
            for _ in range(120):
                noise = np.random.normal(0, 2.0, 3) 
                X.append(np.array(t_lab) + noise)
                y.append(class_idx)
            ndps_map[class_idx] = data.get('ndps', 'N/A')
            labels.append(data['target_compound'])
        model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
        model.fit(np.array(X), np.array(y))
        return model, (labels, ndps_map)
    except: return None, None

# --- 4. COLOR MATH ---
def get_universal_name(rgb):
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 12: return "Neutral Gray"
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
    except: return "Detected Color"

def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

# --- 5. APP UI ---
st.set_page_config(page_title="NCB Field Companion", page_icon="⚖️")

# CSS UI
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top: -55px;}
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1 style="color:white; margin:0;">⚖️ NCB FIELD COMPANION</h1></div>', unsafe_allow_html=True)

# SIDEBAR: Hardware Controls
with st.sidebar:
    st.header("⚙️ Hardware Settings")
    flash_toggle = st.toggle("🔦 Turn on Flashlight", value=False)
    st.divider()
    off_id = st.text_input("Officer ID", "NCB-OFF-101")
    case_no = st.text_input("Case Ref", "F.No-2024/09")
    
# Inject the Flashlight and Auto-Shutdown JS
inject_hardware_controls(flash_toggle)

model, meta = train_ncb_ai()

st.subheader("1. Optical Evidence Capture")
cam_img = st.camera_input("SCAN REAGENT VIAL")

if cam_img:
    img_bytes = cam_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    
    # Process center ROI
    h, w, _ = img.shape
    r = 20
    roi = img[h//2-r:h//2+r, w//2-r:w//2+r]
    avg_rgb = np.mean(roi, axis=(0,1))[::-1]
    lab = rgb_to_lab_scaled(avg_rgb)
    hex_c = '#%02x%02x%02x' % (int(avg_rgb[0]), int(avg_rgb[1]), int(avg_rgb[2]))
    u_name = get_universal_name(avg_rgb)
    
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_c};">
            <h1 style="margin:0; color:white;">{u_name}</h1>
            <p style="margin:0; color:#AAA;"><b>HEX:</b> {hex_c.upper()} | <b>LAB:</b> {lab}</p>
        </div>
    """, unsafe_allow_html=True)

    # Prediction logic (Logistic Regression)
    if model and meta:
        probs = model.predict_proba([lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        if conf > 65:
            drug = meta[0][idx]
            st.success(f"⚖️ AI MATCH: {drug} ({conf:.1f}% Confidence)")
            speech = f"Analysis complete. Probability of {drug} is {conf:.0f} percent."
        else:
            st.warning("Low confidence. No match found.")
            speech = f"Detected {u_name}. No match found."
            
        # Talk Back
        components.html(f'<script>window.speechSynthesis.cancel(); var m = new SpeechSynthesisUtterance("{speech}"); m.lang="en-IN"; window.speechSynthesis.speak(m);</script>', height=0)

    st.write("---")
    if st.button("📄 Generate PDF Report"):
        st.info("Report generation active. (Requires reportlab)")
