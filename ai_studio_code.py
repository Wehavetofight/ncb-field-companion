import streamlit as st
import cv2
import numpy as np
import json
import os
import pytz
from datetime import datetime
from sklearn.linear_model import LogisticRegression
import streamlit.components.v1 as components

# --- 1. DATABASE LOGIC (JSON as a Database) ---
DB_FILE = "reagents.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_to_db(key, data):
    db = load_db()
    db[key] = data
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

# --- 2. AI TRAINING FROM DATABASE ---
@st.cache_resource
def train_ai_from_db():
    db = load_db()
    if len(db) < 2: return None, None
    X, y, labels, metadata = [], [], [], []
    for key, val in db.items():
        # Using the LAB coordinates from the database
        for _ in range(100):
            noise = np.random.normal(0, 2.0, 3)
            X.append(np.array(val['target_lab']) + noise)
            y.append(len(labels))
        labels.append(val['target_compound'])
        metadata.append(val)
    
    model = LogisticRegression(multi_class='multinomial', max_iter=1000)
    model.fit(X, y)
    return model, (labels, metadata)

# --- 3. APP UI ---
st.set_page_config(page_title="NCB Database Companion", layout="centered")

# Load Database
reagent_db = load_db()
kit_list = sorted(list(set([v['reagent'] for v in reagent_db.values()]))) if reagent_db else ["General Scan"]

st.title("⚖️ NCB Field Companion")
st.write(f"Connected to Database: `{DB_FILE}` ({len(reagent_db)} records)")

with st.sidebar:
    st.header("Settings")
    selected_kit = st.selectbox("Active Field Kit", kit_list)
    st.divider()
    
    # --- ADMIN: ADD TO DATABASE ---
    with st.expander("➕ Add New Kit Data"):
        st.write("Register a new reagent color result.")
        new_drug = st.text_input("Substance Name")
        new_reagent = st.text_input("Reagent Kit Name")
        new_ndps = st.text_input("NDPS Section")
        st.info("Scan the color first, then click Save.")
        
# Camera Capture
cam_in = st.camera_input("SCAN REAGENT")

if cam_in:
    # Color Extraction
    img = cv2.imdecode(np.frombuffer(cam_in.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    h, w, _ = img.shape
    roi = img[h//2-10:h//2+10, w//2-10:w//2+10]
    rgb = np.mean(roi, axis=(0,1))[::-1]
    
    # Lab Conversion
    pix = np.uint8([[rgb]])
    lab = cv2.cvtColor(pix, cv2.COLOR_RGB2Lab)[0][0].astype(float)
    standard_lab = [round(lab[0]*(100/255),1), round(lab[1]-128,1), round(lab[2]-128,1)]
    
    # AI Prediction
    model, meta = train_ai_from_db()
    if model:
        probs = model.predict_proba([standard_lab])[0]
        idx = np.argmax(probs)
        conf = probs[idx] * 100
        result = meta[0][idx]
        kit_info = meta[1][idx]

        # Only show match if it belongs to the selected kit
        if kit_info['reagent'] == selected_kit and conf > 70:
            st.success(f"✅ **AI MATCH:** {result} ({conf:.1f}% Confidence)")
            st.info(f"📜 **Statute:** {kit_info['ndps_section']}")
        else:
            st.warning("No high-confidence match for the selected kit.")
    
    # --- ADMIN: SAVE CURRENT COLOR ---
    if st.sidebar.button("💾 Save Scan to Database"):
        if new_drug and new_reagent:
            entry_key = f"{new_reagent}_{new_drug}".lower().replace(" ","_")
            new_entry = {
                "reagent": new_reagent,
                "target_compound": new_drug,
                "target_lab": standard_lab,
                "ndps_section": new_ndps,
                "tolerance_de": 25.0
            }
            save_to_db(entry_key, new_entry)
            st.sidebar.success(f"Saved {new_drug} to Database!")
            st.cache_resource.clear()
            st.rerun()
