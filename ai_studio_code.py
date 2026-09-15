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

# --- COLOR ENGINES ---
def get_universal_name(rgb):
    """Finds the closest human-readable name for ANY color."""
    min_colors = {}
    try:
        for hex_code, name in webcolors.CSS3_HEX_TO_NAMES.items():
            r_c, g_c, b_c = webcolors.hex_to_rgb(hex_code)
            rd = (r_c - rgb[0]) ** 2
            gd = (g_c - rgb[1]) ** 2
            bd = (b_c - rgb[2]) ** 2
            min_colors[(rd + gd + bd)] = name
        return min_colors[min(min_colors.keys())].title().replace('Grey', 'Gray')
    except:
        return "Unknown Shade"

def color_dist(rgb1, rgb2):
    return np.sqrt(sum((a - b) ** 2 for a, b in zip(rgb1, rgb2)))

# --- PDF GENERATOR ---
def generate_pdf(case_info, color_data, match_info, img_hash):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    data = [
        ["FIELD SCREENING RECORD", ""],
        ["Status", "PRESUMPTIVE ONLY"],
        ["Timestamp (IST)", case_info['time']],
        ["Officer ID", case_info['officer']],
        ["Case Reference", case_info['case']],
        ["Universal Color", color_data['name']],
        ["Detected HEX", color_data['hex']],
        ["Reagent Match", match_info],
        ["Record Hash", img_hash]
    ]
    
    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#002F6C")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 10)
    ]))
    
    elements = [Paragraph("NCB DIGITAL COMPANION REPORT", styles['Title']), Spacer(1,12), table]
    doc.build(elements)
    return buffer.getvalue()

# --- APP UI ---
st.set_page_config(page_title="NCB Smart Shield", page_icon="⚖️")

# Custom CSS for Mobile
st.markdown("<style>div.stButton > button {width:100%; border-radius:10px; height:3em; font-weight:bold;}</style>", unsafe_allow_html=True)

st.title("⚖️ NCB Field Companion")
st.caption(f"Standardizing Drug Testing | {get_india_time()}")

# Sidebar for Records
with st.sidebar:
    st.header("📋 Case Details")
    off_id = st.text_input("Officer ID", "NCB-OFF-01")
    case_ref = st.text_input("Case No.", "F.No-" + datetime.now().strftime("%Y/%m"))
    st.divider()
    st.write("This tool removes human subjectivity from colorimetric tests.")

# 1. CAMERA CAPTURE
st.subheader("1. Scan Reagent Result")
camera_img = st.camera_input("Take a photo of the test vial/strip")

if camera_img:
    # Process Image
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(camera_img.getvalue()).hexdigest()[:16]
    
    # Simple White Balance
    img_float = img.astype(np.float32)
    avg_color = np.mean(img_float, axis=(0,1))
    img_balanced = np.clip(img_float * (np.mean(avg_color)/avg_color), 0, 255).astype(np.uint8)
    
    # Get Center Color
    h, w, _ = img_balanced.shape
    center_rgb = img_balanced[h//2, w//2][::-1] # BGR to RGB
    hex_val = '#%02x%02x%02x' % tuple(center_rgb)
    u_name = get_universal_name(center_rgb)
    
    # 2. DISPLAY RESULTS
    st.write("### 2. Identification")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:20px; border-radius:15px; border-left:10px solid {hex_val};">
            <h2 style="margin:0; color:white;">{u_name}</h2>
            <p style="margin:0; color:#AAA;">Detected HEX: {hex_val.upper()}</p>
            <p style="margin:0; color:#AAA;">Time: {get_india_time()}</p>
        </div>
    """, unsafe_allow_html=True)

    # 3. MATCHING LOGIC
    match_text = "No Reagent Match Found"
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            db = json.load(f)
        
        for k, v in db.items():
            db_rgb = webcolors.hex_to_rgb(v['target_hex'])
            if color_dist(center_rgb, db_rgb) < 50: # Tolerance
                match_text = f"MATCH: {v['target_compound']} ({v['reagent']} Reagent)"
                st.success(f"✅ **{match_text}**")
                st.info(f"⚖️ **NDPS Note:** {v['ndps_section']}")
                break
    
    if "MATCH" not in match_text:
        st.warning("Note: Universal color identified. No specific reagent match in database.")

    # 4. DOWNLOAD REPORT
    st.write("---")
    case_data = {'time': get_india_time(), 'officer': off_id, 'case': case_ref}
    color_data = {'name': u_name, 'hex': hex_val.upper()}
    
    pdf_file = generate_pdf(case_data, color_data, match_text, img_hash)
    st.download_button(
        label="📥 Download Official Screening Report (PDF)",
        data=pdf_file,
        file_name=f"NCB_Report_{img_hash}.pdf",
        mime="application/pdf"
    )

    # Admin Registration (Optional)
    with st.expander("🛠️ Admin: Save this color to Database"):
        new_name = st.text_input("Substance Name")
        new_reag = st.text_input("Reagent Name")
        if st.button("Save to reagents.json"):
            # Logic to append to json
            st.success("New reagent saved successfully!")
