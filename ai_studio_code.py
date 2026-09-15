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

# --- 1. PRO APP STYLING (CSS) ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️", layout="centered")

st.markdown("""
    <style>
    /* Hide Streamlit Header and Footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Make the background look like a professional app */
    .stApp {
        background-color: #0E1117;
    }
    
    /* Style the buttons to be big and touch-friendly */
    .stButton>button {
        width: 100%;
        border-radius: 15px;
        height: 4em;
        background-color: #002F6C;
        color: white;
        border: 2px solid #4E9F3D;
        font-size: 20px;
        font-weight: bold;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.3);
    }
    
    /* Style the Camera Input area */
    .stCameraInput {
        border-radius: 15px;
        overflow: hidden;
        border: 2px solid #444;
    }

    /* Custom Header for the App */
    .app-header {
        background-color: #002F6C;
        padding: 20px;
        border-radius: 0 0 25px 25px;
        text-align: center;
        margin-top: -60px;
        margin-bottom: 20px;
        border-bottom: 3px solid #4E9F3D;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. THE REST OF YOUR LOGIC (Same as before) ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

def talk_back(text):
    components.html(f"""
        <script>
        window.speechSynthesis.cancel(); 
        var msg = new SpeechSynthesisUtterance("{text}");
        msg.lang = 'en-IN';
        window.speechSynthesis.speak(msg);
        </script>
    """, height=0)

def get_universal_name(rgb):
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    colors_db = {
        "Pure White": (255, 255, 255), "Silver": (192, 192, 192), "Jet Black": (15, 15, 15),
        "Deep Red": (150, 0, 0), "Golden Yellow": (255, 215, 0), "Emerald Green": (0, 150, 0),
        "Cobalt Blue": (0, 71, 171), "Deep Purple": (128, 0, 128), "Brown": (139, 69, 19)
    }
    best_match = "Detected Shade"
    min_dist = float('inf')
    for name, c_rgb in colors_db.items():
        dist = np.sqrt((c_rgb[0]-r)**2 + (c_rgb[1]-g)**2 + (c_rgb[2]-b)**2)
        if dist < min_dist:
            min_dist = dist
            best_match = name
    return best_match

def rgb_to_lab_scaled(rgb):
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB2Lab)
    l, a, b = pixel_lab[0][0].astype(float)
    return [round(l * (100/255), 1), round(a - 128, 1), round(b - 128, 1)]

# --- UI LAYOUT ---
# Custom App Bar
st.markdown('<div class="app-header"><h1 style="color:white; margin:0;">⚖️ NCB COMPANION</h1><p style="color:#4E9F3D; margin:0;">Forensic Intelligence Unit</p></div>', unsafe_allow_html=True)

st.caption(f"IST: {get_india_time()}")

camera_img = st.camera_input("SCAN SAMPLE")

if camera_img:
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1]
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:20px; border-left:12px solid {hex_val}; margin-top:20px;">
            <h1 style="margin:0; color:white; font-size: 2.5em;">{u_name}</h1>
            <p style="margin:0; color:#AAA;">HEX: {hex_val.upper()} | L:{center_lab[0]} a:{center_lab[1]} b:{center_lab[2]}</p>
        </div>
    """, unsafe_allow_html=True)

    match_text = "No drug match found."
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: db = json.load(f)
        for k, v in db.items():
            if v.get('target_lab') and np.sqrt(np.sum((np.array(center_lab) - np.array(v['target_lab']))**2)) < 25:
                match_text = f"Result: {v['target_compound']}"
                st.success(f"✅ **{match_text}**")
                break
    
    talk_back(f"Detected {u_name}. {match_text}")
    
    if st.button("🔊 REPEAT AUDIO"):
        talk_back(f"Detected {u_name}. {match_text}")

with st.sidebar:
    st.header("Settings")
    st.text_input("Officer ID", "NCB-442")
    st.text_input("Case No.", "F-2024/09")
