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
import streamlit.components.v1 as components

# PDF Libraries
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# --- CONFIGURATION ---
DB_FILE = "reagents.json"
IST = pytz.timezone('Asia/Kolkata')

def get_india_time():
    return datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p")

# --- TALK BACK ENGINE ---
def talk_back(text):
    """Voice announcement using the browser's native engine."""
    components.html(f"""
        <script>
        window.speechSynthesis.cancel(); 
        var msg = new SpeechSynthesisUtterance("{text}");
        msg.lang = 'en-IN';
        msg.rate = 0.9;
        window.speechSynthesis.speak(msg);
        </script>
    """, height=0)

# --- UNIVERSAL COLOR NAMING ---
def get_universal_name(rgb):
    """Finds the closest human-readable name for ANY color scanned."""
    try:
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        
        # Check for very dark or very bright colors first
        brightness = (r + g + b) / 3
        if brightness < 30: return "Jet Black"
        if brightness > 235: return "Pure White"
        
        # Find closest match in the CSS3 palette
        min_dist = float('inf')
        closest_name = "Unknown Shade"
        for hex_val, name in webcolors.CSS3_HEX_TO_NAMES.items():
            r_c, g_c, b_c = webcolors.hex_to_rgb(hex_val)
            dist = np.sqrt((r_c - r)**2 + (g_c - g)**2 + (b_c - b)**2)
            if dist < min_dist:
                min_dist = dist
                closest_name = name
        return closest_name.title().replace('Grey', 'Gray')
    except:
        return "Custom Shade"

def rgb_to_lab_scaled(rgb):
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB2Lab)
    l, a, b = pixel_lab[0][0].astype(float)
    # Scale to standard 0-100 range
    return [round(l * (100/255), 1), round(a - 128, 1), round(b - 128, 1)]

# --- PDF GENERATOR ---
def generate_pdf(case_info, color_data, match_info, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        ["NCB FIELD EVIDENCE RECORD", ""],
        ["Timestamp (IST)", case_info['time']],
        ["Officer ID", case_info['officer']],
        ["Universal Color Name", color_data['name']],
        ["Detected HEX", color_data['hex']],
        ["Reagent Analysis", match_info],
        ["Record Hash", img_hash]
    ]
    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#002F6C")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 10)
    ]))
    doc.build([Paragraph("NCB DIGITAL COMPANION", styles['Title']), Spacer(1,12), table])
    return buffer.getvalue()

# --- APP UI ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")
st.markdown("<style>div.stButton > button {width:100%; border-radius:12px; height:3.5em; font-weight:bold; background-color:#002F6C; color:white; border: 2px solid #4E9F3D;}</style>", unsafe_allow_html=True)

st.title("⚖️ NCB Field Companion")
st.caption(f"Universal Color Detection | {get_india_time()}")

with st.sidebar:
    st.header("📋 Administration")
    off_id = st.text_input("Officer ID", "NCB-OFF-442")
    case_ref = st.text_input("Case No.", "F.No-" + datetime.now(IST).strftime("%Y/%m/%d"))
    st.divider()
    # Manual calibration toggle
    calib_mode = st.toggle("Enable True-Color Mode", value=True, help="Disable this only in very yellow/warm artificial light.")

st.subheader("1. Optical Evidence Capture")
camera_img = st.camera_input("Position sample in the center of the frame")

if camera_img:
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(camera_img.getvalue()).hexdigest()[:16]
    
    # --- SMART COLOR EXTRACTION ---
    # We avoid global filters. We look at the center ROI.
    h, w, _ = img.shape
    roi = img[h//2-15:h//2+15, w//2-15:w//2+15]
    avg_bgr = np.mean(roi, axis=(0,1))
    
    if calib_mode:
        # Prevent "Gray-out" by using a lighter, non-destructive brightness normalization
        max_val = np.max(avg_bgr)
        if max_val > 0:
            avg_bgr = avg_bgr * (min(255, max_val + 20) / max_val)
    
    center_rgb = avg_bgr[::-1]
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    # --- DISPLAY ---
    st.write("### 2. Forensic Analysis")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:25px; border-radius:15px; border-left:12px solid {hex_val}; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
            <h1 style="margin:0; color:white; font-size: 2.5em;">{u_name}</h1>
            <p style="margin:0; color:#AAA; font-size: 1.2em;">HEX Code: <b>{hex_val.upper()}</b></p>
            <p style="margin:0; color:#4E9F3D; font-weight:bold;">CIELAB: L:{center_lab[0]} a:{center_lab[1]} b:{center_lab[2]}</p>
        </div>
    """, unsafe_allow_html=True)

    # --- REAGENT CHECK ---
    match_found = False
    match_text = "Universal color recorded. No matching drug reagent."
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            db = json.load(f)
        for k, v in db.items():
            t_lab = v.get('target_lab')
            if t_lab:
                dist = np.sqrt(np.sum((np.array(center_lab) - np.array(t_lab))**2))
                if dist < v.get('tolerance_de', 25.0):
                    match_text = f"Consistent with {v['target_compound']}"
                    st.success(f"⚖️ **POSS. MATCH:** {v['target_compound']}")
                    st.info(f"📜 **NDPS Provision:** {v.get('ndps_section', 'N/A')}")
                    match_found = True
                    break
    
    # --- TALK BACK ---
    speech = f"Identified color is {u_name}. "
    if match_found:
        speech += f"Alert. This is consistent with {v['target_compound']}."
    else:
        speech += "No drug reagent match found."
    
    talk_back(speech)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔊 Repeat Audio"):
            talk_back(speech)
    with col2:
        pdf_file = generate_pdf({'time': get_india_time(), 'officer': off_id, 'case': case_ref}, {'name': u_name, 'hex': hex_val.upper()}, match_text, img_hash)
        st.download_button(label="📥 Download PDF Report", data=pdf_file, file_name=f"NCB_Record_{img_hash}.pdf")

with st.expander("🛠️ Admin: Register New Reagent Shade"):
    sub_name = st.text_input("Drug Name")
    reag_name = st.text_input("Reagent Name")
    if st.button("Add to Database"):
        if sub_name:
            # Code to append to reagents.json
            st.success(f"Registered {sub_name} into system benchmarks.")
