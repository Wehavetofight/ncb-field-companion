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
    """Finds a human-readable name for display using RGB."""
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

def rgb_to_lab(rgb):
    """Converts RGB pixel to CIELAB space for scientific matching."""
    # Create a 1x1 pixel image
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB@Lab)
    return pixel_lab[0][0].astype(float)

def calculate_de(lab1, lab2):
    """Calculates Delta E (Color distance) between two Lab colors."""
    return np.sqrt(np.sum((np.array(lab1) - np.array(lab2))**2))

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
        ["Result", match_info],
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
st.markdown("<style>div.stButton > button {width:100%; border-radius:10px; height:3em; font-weight:bold;}</style>", unsafe_allow_html=True)

st.title("⚖️ NCB Field Companion")
st.caption(f"Presumptive Screening Aid | {get_india_time()}")

with st.sidebar:
    st.header("📋 Case Details")
    off_id = st.text_input("Officer ID", "NCB-DEL-442")
    case_ref = st.text_input("Case No.", "F.No-" + datetime.now(IST).strftime("%Y/%m/%d"))

st.subheader("1. Sample Evidence Capture")
camera_img = st.camera_input("Scan Reagent Vial/Strip")

if camera_img:
    file_bytes = np.frombuffer(camera_img.getvalue(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    img_hash = hashlib.sha256(camera_img.getvalue()).hexdigest()[:16]
    
    # Process color
    img_float = img.astype(np.float32)
    avg_color = np.mean(img_float, axis=(0,1))
    img_balanced = np.clip(img_float * (np.mean(avg_color)/avg_color), 0, 255).astype(np.uint8)
    
    h, w, _ = img_balanced.shape
    center_rgb = img_balanced[h//2, w//2][::-1] # RGB
    center_lab = rgb_to_lab(center_rgb) # Convert to LAB for matching
    hex_val = '#%02x%02x%02x' % tuple(center_rgb)
    u_name = get_universal_name(center_rgb)
    
    st.write("### 2. Analysis Result")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:20px; border-radius:15px; border-left:10px solid {hex_val};">
            <h2 style="margin:0; color:white;">{u_name}</h2>
            <p style="margin:0; color:#AAA;">Detected HEX: {hex_val.upper()}</p>
            <p style="margin:0; color:#AAA;">CIE Lab: L:{center_lab[0]:.1f} a:{center_lab[1]:.1f} b:{center_lab[2]:.1f}</p>
        </div>
    """, unsafe_allow_html=True)

    # MATCHING LOGIC (Matching against your LAB values)
    match_found = False
    match_text = "No Reagent Match Found"
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            db = json.load(f)
        
        for k, v in db.items():
            target_lab = v.get('target_lab')
            if target_lab:
                # Calculate scientific Delta E distance
                dist = calculate_de(center_lab, target_lab)
                tolerance = v.get('tolerance_de', 20.0)
                
                if dist < tolerance:
                    match_text = f"Consistent with {v['target_compound']}"
                    st.success(f"✅ **POSS. MATCH:** {v['target_compound']}")
                    st.info(f"🧬 **Reagent:** {v['reagent']} | **NDPS:** {v['ndps_section']}")
                    match_found = True
                    break
    
    if not match_found:
        st.warning("Result: Universal color recorded. No matching reagent reference in database.")

    st.write("---")
    case_data = {'time': get_india_time(), 'officer': off_id, 'case': case_ref}
    color_data = {'name': u_name, 'hex': hex_val.upper()}
    pdf_file = generate_pdf(case_data, color_data, match_text, img_hash)
    st.download_button(label="📥 Download Official Screening Report (PDF)", data=pdf_file, file_name=f"NCB_Report.pdf", mime="application/pdf")

# --- ADMIN SECTION ---
with st.expander("🛠️ Admin: Register Current Color into Database"):
    st.write("This will save the current camera color as a new reagent benchmark.")
    new_sub = st.text_input("Substance (e.g., MDMA)")
    new_reag = st.text_input("Reagent (e.g., Marquis)")
    new_ndps = st.text_input("NDPS Section")
    
    if st.button("Save Profile"):
        if camera_img and new_sub:
            current_db = {}
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "r") as f: current_db = json.load(f)
            
            entry_id = f"{new_reag}_{new_sub}".replace(" ", "_")
            current_db[entry_id] = {
                "reagent": new_reag,
                "target_compound": new_sub,
                "color_name": u_name,
                "target_lab": [float(center_lab[0]), float(center_lab[1]), float(center_lab[2])],
                "tolerance_de": 20.0,
                "ndps_section": new_ndps
            }
            with open(DB_FILE, "w") as f: json.dump(current_db, f, indent=2)
            st.success("New reagent profile saved! Please refresh.")
        else:
            st.error("Capture a photo and enter substance name first.")
