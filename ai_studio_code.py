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
NCB_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Narcotics_Control_Bureau_logo.png/220px-Narcotics_Control_Bureau_logo.png"

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

def talk_back(text):
    components.html(f"""<script>window.speechSynthesis.cancel(); var msg = new SpeechSynthesisUtterance("{text}"); msg.lang = 'en-IN'; msg.rate = 0.9; window.speechSynthesis.speak(msg);</script>""", height=0)

@st.cache_resource
def load_reagent_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return json.load(f)
    return {}

def rgb_to_lab_scaled(rgb):
    pixel_lab = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2Lab)[0][0]
    return [round(float(pixel_lab[0]*(100/255)),1), round(float(pixel_lab[1]-128),1), round(float(pixel_lab[2]-128),1)]

def get_universal_name(rgb):
    r, g, b = [int(x) for x in rgb]
    diff = max(r, g, b) - min(r, g, b)
    if diff < 12: return "Neutral Gray/White"
    try:
        min_dist = float('inf')
        closest_name = "Unknown Shade"
        for hex_val, name in webcolors.CSS3_HEX_TO_NAMES.items():
            r_c, g_c, b_c = webcolors.hex_to_rgb(hex_val)
            dist = (r_c - r)**2 + (g_c - g)**2 + (b_c - b)**2
            if dist < min_dist:
                min_dist = dist
                closest_name = name
        return closest_name.title().replace('Grey', 'Gray')
    except: return "Detected Shade"

# --- APP UI ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")
st.markdown("""<style>.stApp { background-color: #0E1117; } .main-header { background-color: #002F6C; padding: 20px; border-radius: 10px; text-align: center; border-bottom: 4px solid #4E9F3D; margin-top:-50px; } .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #002F6C; color: white; font-weight: bold; border: 1px solid #4E9F3D; }</style>""", unsafe_allow_html=True)

st.markdown(f'<div class="main-header"><img src="{NCB_LOGO}" width="70"><h1 style="color:white; margin:0;">NCB FIELD COMPANION</h1></div>', unsafe_allow_html=True)
st.caption(f"Works with Marquis, Scott, & Duquenois Kits | {get_india_time()}")

db = load_reagent_db()

with st.sidebar:
    st.header("📋 Case Details")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    # THE KEY FEATURE: Select the Kit being used
    kit_list = sorted(list(set([v['reagent'] for v in db.values()]))) if db else ["Marquis", "Scott", "Duquenois-Levine"]
    selected_kit = st.selectbox("Select Field Kit Used", kit_list)
    st.info(f"App will now calibrate for {selected_kit} reactions.")

st.subheader(f"1. Scan {selected_kit} Reagent Result")
camera_img = st.camera_input("Place vial/strip in center")

if camera_img:
    img_bytes = camera_img.getvalue()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1]
    lab = rgb_to_lab_scaled(center_rgb)
    hex_c = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""<div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_c};"><h1 style="margin:0; color:white;">{u_name}</h1><p style="margin:0; color:#AAA;"><b>HEX:</b> {hex_c.upper()} | <b>LAB:</b> {lab}</p></div>""", unsafe_allow_html=True)

    # MATCHING LOGIC: Filtered by the selected Kit
    match_found = False
    speech = f"Detected shade is {u_name}."
    
    for k, v in db.items():
        if v['reagent'] == selected_kit:
            dist = np.sqrt(np.sum((np.array(lab) - np.array(v['target_lab']))**2))
            if dist < v.get('tolerance_de', 25.0):
                st.success(f"⚖️ **POSS. MATCH:** {v['target_compound']} (via {selected_kit} Kit)")
                st.info(f"📜 **NDPS Provision:** {v.get('ndps_section', 'N/A')}")
                speech += f" Result consistent with {v['target_compound']} using {selected_kit} reagent."
                match_found = True
                break
                
    if not match_found:
        st.warning(f"No match found for {selected_kit} kit expected colors.")
        speech += f" No match found for {selected_kit} kit."

    talk_back(speech)
    
    # PDF generation logic remains same as previous version...
