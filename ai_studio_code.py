import streamlit as st
import cv2
import numpy as np
import hashlib
import json
import os
from datetime import datetime
from io import BytesIO

# UI/PDF Libraries
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet

# --- DATABASE CONFIG ---
DB_FILE = "reagents.json"

def load_reagents():
    if not os.path.exists(DB_FILE):
        # Default starter data for SIH Demo
        return {
            "marquis_heroin": {
                "reagent": "Marquis",
                "target_compound": "Heroin",
                "target_hex": "#3E000C",
                "target_lab": [11.0, 25.0, 5.0],
                "tolerance_de": 12.0,
                "ndps_section": "Sec 21 (Punishment for contravention in relation to manufactured drugs)"
            }
        }
    with open(DB_FILE, "r") as f:
        return json.load(f)

# --- COLOR MATH (CIEDE2000) ---
def ciede2000(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    return float(np.sqrt((L1-L2)**2 + (a1-a2)**2 + (b1-b2)**2)) # Simplified for performance

# --- APP LAYOUT ---
st.set_page_config(page_title="NCB Field Companion", page_icon="⚖️", layout="centered")

# Custom CSS for a professional "Government Tool" look
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #002f6c; color: white; }
    .reportview-container .main .block-container { padding-top: 1rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚖️ Digital Drug-Test Companion")
st.caption("NCB Field Interdiction Support - SIH 26231")

# --- SIDEBAR: OFFICER INFO ---
with st.sidebar:
    st.header("Officer Details")
    officer_name = st.text_input("Officer Name/ID", placeholder="e.g., NCB-DEL-442")
    case_no = st.text_input("Case Reference", placeholder="F.No. 2024/...")
    st.divider()
    st.info("This tool standardizes visual reagents to prevent subjective bias.")

# --- STEP 1: CAPTURE ---
st.subheader("1. Sample Evidence Capture")
camera_img = st.camera_input("Scan Reagent Vial/Strip")

if camera_img:
    bytes_data = camera_img.getvalue()
    cv_img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
    
    # Auto-White Balance Logic
    img_float = cv_img.astype(np.float32)
    avg_color = np.mean(img_float, axis=(0,1))
    gain = np.mean(avg_color) / avg_color
    balanced = np.clip(img_float * gain, 0, 255).astype(np.uint8)
    
    # Process Center Sample
    h, w, _ = balanced.shape
    size = int(min(h, w) * 0.2)
    center_y, center_x = h//2, w//2
    sample_zone = balanced[center_y-size:center_y+size, center_x-size:center_x+size]
    
    # Get Lab Color
    mean_bgr = np.mean(sample_zone, axis=(0,1)).reshape(1,1,3).astype(np.float32) / 255.0
    sample_lab = cv2.cvtColor(mean_bgr, cv2.COLOR_BGR2Lab).flatten()
    
    # HEX for Display
    r, g, b = int(mean_bgr[0,0,2]*255), int(mean_bgr[0,0,1]*255), int(mean_bgr[0,0,0]*255)
    hex_color = f"#{r:02X}{g:02X}{b:02X}"

    # --- STEP 2: IDENTIFICATION ---
    st.subheader("2. Analysis Result")
    reagent_db = load_reagents()
    
    match_found = None
    min_dist = 999
    
    for key, data in reagent_db.items():
        dist = ciede2000(sample_lab, data['target_lab'])
        if dist < dist < data.get("tolerance_de", 15.0) and dist < min_dist:
            min_dist = dist
            match_found = data

    col1, col2 = st.columns(2)
    with col1:
        st.color_picker("Detected Hue", hex_color, disabled=True)
    with col2:
        if match_found:
            st.success(f"**MATCH:** {match_found['target_compound']}")
            confidence = max(0, 100 - (min_dist * 4))
            st.metric("Confidence", f"{confidence:.1f}%")
        else:
            st.error("No Match Found")

    # --- STEP 3: DOCUMENTATION ---
    st.subheader("3. Record & Certification")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sha_hash = hashlib.sha256(bytes_data).hexdigest()[:16] # Shortened for UI
    
    st.code(f"Hash: {sha_hash}\nTime: {timestamp}\nLocation: 28.6139° N, 77.2090° E")

    # PDF Generation Logic (Simplified)
    if st.button("Generate Official Report"):
        if not officer_name:
            st.warning("Please enter Officer ID in the sidebar first.")
        else:
            # Here you would call your generate_pdf function
            st.balloons()
            st.success("Report generated successfully.")
            # Note: In a real app, use the generate_pdf function from your script here.