import streamlit as st
import cv2
import numpy as np
import hashlib
import json
import os
import pytz
from datetime import datetime
from io import BytesIO
import streamlit.components.v1 as components

# --- CONFIGURATION ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# --- REFINED TALK BACK ---
def talk_back(text):
    """Voice announcement using native Browser Synthesis."""
    components.html(f"""
        <script>
        window.speechSynthesis.cancel(); 
        var msg = new SpeechSynthesisUtterance("{text}");
        msg.lang = 'en-IN';
        msg.pitch = 1;
        msg.rate = 0.9;
        window.speechSynthesis.speak(msg);
        </script>
    """, height=0)

# --- INTERNAL ROBUST COLOR NAMING ENGINE ---
def get_universal_name(rgb):
    """Built-in naming engine: No external library required, zero failure."""
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    
    # 1. Forensic Color Palette (Common reagent outcomes + universal shades)
    colors_db = {
        "Pure White": (255, 255, 255), "Ivory": (255, 255, 240), "Silver": (192, 192, 192),
        "Dark Gray": (169, 169, 169), "Jet Black": (15, 15, 15), "Deep Crimson": (153, 0, 0),
        "Bright Red": (255, 0, 0), "Maroon": (128, 0, 0), "Blood Orange": (255, 69, 0),
        "Golden Yellow": (255, 215, 0), "Amber": (255, 191, 0), "Olive Green": (128, 128, 0),
        "Emerald Green": (80, 200, 120), "Forest Green": (34, 139, 34), "Deep Cyan": (0, 139, 139),
        "Cobalt Blue": (0, 71, 171), "Royal Blue": (65, 105, 225), "Navy Blue": (0, 0, 128),
        "Indigo": (75, 0, 130), "Deep Purple": (128, 0, 128), "Violet": (238, 130, 238),
        "Magenta": (255, 0, 255), "Pink": (255, 192, 203), "Brown": (139, 69, 19),
        "Tan": (210, 180, 140), "Slate": (112, 128, 144), "Pale Blue": (173, 216, 230)
    }

    best_match = "Unknown Shade"
    min_dist = float('inf')
    
    for name, c_rgb in colors_db.items():
        dist = np.sqrt((c_rgb[0]-r)**2 + (c_rgb[1]-g)**2 + (c_rgb[2]-b)**2)
        if dist < min_dist:
            min_dist = dist
            best_match = name

    # Fine-tuning for neutrals (if RGB values are very close together)
    diff = max(r, g, b) - min(r, g, b)
    if diff < 15:
        if r > 200: return "Off-White"
        if r < 40: return "Charcoal Black"
        return "Neutral Gray"

    return best_match

def rgb_to_lab_scaled(rgb):
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB2Lab)
    l, a, b = pixel_lab[0][0].astype(float)
    return [round(l * (100/255), 1), round(a - 128, 1), round(b - 128, 1)]

# --- APP UI ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")
st.markdown("<style>div.stButton > button {width:100%; border-radius:12px; height:3.5em; font-weight:bold; background-color:#002F6C; color:white; border: 1px solid #4E9F3D;}</style>", unsafe_allow_html=True)

st.title("⚖️ NCB Field Companion")
st.caption(f"Refined Forensic Screening | {get_india_time()}")

with st.sidebar:
    st.header("📋 Records")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    case_ref = st.text_input("Case No.", "F.No-" + datetime.now(IST).strftime("%Y/%m/%d"))
    st.divider()
    lighting_boost = st.slider("Brightness Adjustment", 0.8, 1.5, 1.0)
    st.info("Adjust if the environment is too dark.")

st.subheader("1. Optical Evidence Capture")
camera_img = st.camera_input("Place the sample vial/strip in center")

if camera_img:
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    
    # --- REFINED COLOR EXTRACTION ---
    h, w, _ = img.shape
    # Sample a 30x30 area from center
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_bgr = np.mean(roi, axis=(0,1)) * lighting_boost
    avg_bgr = np.clip(avg_bgr, 0, 255)
    
    center_rgb = avg_bgr[::-1]
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    # --- UI DISPLAY ---
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_val};">
            <h1 style="margin:0; color:white; font-size: 2.8em;">{u_name}</h1>
            <p style="margin:0; color:#AAA; font-size: 1.2em;">HEX: <b>{hex_val.upper()}</b></p>
            <p style="margin:0; color:#4E9F3D; font-weight:bold;">CIELAB Standards: L:{center_lab[0]} a:{center_lab[1]} b:{center_lab[2]}</p>
        </div>
    """, unsafe_allow_html=True)

    # --- REAGENT CHECK ---
    match_found = False
    match_text = f"Universal shade detected as {u_name}. No reagent match."
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            db = json.load(f)
        for k, v in db.items():
            t_lab = v.get('target_lab')
            if t_lab:
                dist = np.sqrt(np.sum((np.array(center_lab) - np.array(t_lab))**2))
                if dist < v.get('tolerance_de', 25.0):
                    match_text = f"Match found. Consistent with {v['target_compound']}."
                    st.success(f"⚖️ **POSS. MATCH:** {v['target_compound']}")
                    st.info(f"📜 **NDPS Provision:** {v.get('ndps_section', 'N/A')}")
                    match_found = True
                    break
    
    # --- VOICE ANNOUNCEMENT ---
    speech = f"Detected shade is {u_name}. " + match_text
    talk_back(speech)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔊 Repeat Audio"):
            talk_back(speech)
    with col2:
        st.button("📄 Generate Report", disabled=True) # Placeholder

    st.write("---")
