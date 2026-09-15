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

# --- IMPROVED COLOR NAMING ENGINE ---
def get_universal_name(rgb):
    """Finds the closest human-readable color name. Built to never fail."""
    try:
        # 1. Convert numpy values to standard python integers
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        
        # 2. Try using the webcolors library
        min_dist = float('inf')
        closest_name = None
        
        # Iterating through CSS3 colors
        for hex_val, name in webcolors.CSS3_HEX_TO_NAMES.items():
            r_c, g_c, b_c = webcolors.hex_to_rgb(hex_val)
            # Euclidean distance
            dist = np.sqrt((r_c - r)**2 + (g_c - g)**2 + (b_c - b)**2)
            if dist < min_dist:
                min_dist = dist
                closest_name = name
        
        if closest_name:
            return closest_name.title().replace('Grey', 'Gray')
            
    except Exception:
        pass

    # 3. FALLBACK: Simple hardcoded palette if the library fails
    fallback_palette = {
        "White": (255, 255, 255), "Black": (0, 0, 0), "Gray": (128, 128, 128),
        "Silver": (192, 192, 192), "Red": (255, 0, 0), "Maroon": (128, 0, 0),
        "Yellow": (255, 255, 0), "Olive": (128, 128, 0), "Lime": (0, 255, 0),
        "Green": (0, 128, 0), "Aqua": (0, 255, 255), "Teal": (0, 128, 128),
        "Blue": (0, 0, 255), "Navy": (0, 0, 128), "Fuchsia": (255, 0, 255),
        "Purple": (128, 0, 128), "Orange": (255, 165, 0), "Brown": (165, 42, 42)
    }
    
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    best_match = "Unknown Shade"
    min_d = 1000000
    for name, color in fallback_palette.items():
        d = (color[0]-r)**2 + (color[1]-g)**2 + (color[2]-b)**2
        if d < min_d:
            min_d = d
            best_match = name
    return best_match

def rgb_to_lab_scaled(rgb):
    """Converts RGB to CIELAB and scales to standard 0-100 range."""
    pixel_rgb = np.uint8([[rgb]])
    pixel_lab = cv2.cvtColor(pixel_rgb, cv2.COLOR_RGB2Lab)
    l, a, b = pixel_lab[0][0].astype(float)
    # Scale to standard Lab ranges
    standard_l = l * (100/255)
    standard_a = a - 128
    standard_b = b - 128
    return [round(standard_l, 1), round(standard_a, 1), round(standard_b, 1)]

def calculate_de(lab1, lab2):
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
        ["Detected Shade", color_data['name']],
        ["Detected HEX", color_data['hex']],
        ["Analysis Result", match_info],
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
st.markdown("<style>div.stButton > button {width:100%; border-radius:10px; height:3.5em; font-weight:bold; background-color:#002F6C; color:white;}</style>", unsafe_allow_html=True)

st.title("⚖️ NCB Field Companion")
st.caption(f"Presumptive Screening Aid | {get_india_time()}")

with st.sidebar:
    st.header("📋 Case Details")
    off_id = st.text_input("Officer ID", "NCB-OFF-101")
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
    roi = img_balanced[h//2-10:h//2+10, w//2-10:w//2+10] # Slightly larger sample area
    avg_bgr = np.mean(roi, axis=(0,1))
    center_rgb = avg_bgr[::-1]
    
    # Calculate values
    center_lab = rgb_to_lab_scaled(center_rgb)
    hex_val = '#%02x%02x%02x' % (int(center_rgb[0]), int(center_rgb[1]), int(center_rgb[2]))
    u_name = get_universal_name(center_rgb)
    
    st.write("### 2. Analysis Result")
    st.markdown(f"""
        <div style="background:#1E1E1E; padding:20px; border-radius:15px; border-left:10px solid {hex_val};">
            <h1 style="margin:0; color:white; font-size: 2.2em;">{u_name}</h1>
            <p style="margin:0; color:#AAA; font-size: 1.1em;">Detected HEX: <b>{hex_val.upper()}</b></p>
            <p style="margin:0; color:#4E9F3D; font-weight:bold;">CIELAB: L:{center_lab[0]} a:{center_lab[1]} b:{center_lab[2]}</p>
        </div>
    """, unsafe_allow_html=True)

    match_found = False
    match_text = "No Reagent Match Found"
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            db = json.load(f)
        
        for k, v in db.items():
            target_lab = v.get('target_lab')
            if target_lab:
                dist = calculate_de(center_lab, target_lab)
                tolerance = v.get('tolerance_de', 25.0)
                
                if dist < tolerance:
                    match_text = f"Consistent with {v['target_compound']}"
                    st.success(f"✅ **POSS. MATCH:** {v['target_compound']}")
                    st.info(f"🧬 **Reagent:** {v['reagent']} | **NDPS:** {v['ndps_section']}")
                    match_found = True
                    break
    
    if not match_found:
        st.warning("Result: Universal color recorded. No matching drug reagent in database.")

    st.write("---")
    case_data = {'time': get_india_time(), 'officer': off_id, 'case': case_ref}
    color_data = {'name': u_name, 'hex': hex_val.upper()}
    pdf_file = generate_pdf(case_data, color_data, match_text, img_hash)
    st.download_button(label="📥 Download Official Report (PDF)", data=pdf_file, file_name=f"NCB_Report.pdf", mime="application/pdf")

with st.expander("🛠️ Admin: Register Current Color"):
    new_sub = st.text_input("Substance")
    new_reag = st.text_input("Reagent")
    new_ndps = st.text_input("NDPS Section")
    if st.button("Save to Database"):
        if camera_img and new_sub:
            current_db = {}
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "r") as f: current_db = json.load(f)
            entry_id = f"{new_reag}_{new_sub}".replace(" ", "_").lower()
            current_db[entry_id] = {
                "reagent": new_reag,
                "target_compound": new_sub,
                "target_lab": center_lab,
                "tolerance_de": 25.0,
                "ndps_section": new_ndps
            }
            with open(DB_FILE, "w") as f: json.dump(current_db, f, indent=2)
            st.success("Saved! Refresh the page to see the match.")
