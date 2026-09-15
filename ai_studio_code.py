import streamlit as st
import streamlit.components.v1 as components
import cv2
import numpy as np
import pandas as pd
import json
import hashlib
import tempfile
import os

from datetime import datetime
import pytz

from PIL import ImageColor

from reportlab.platypus import SimpleDocTemplate, Paragraph, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

import pyttsx3

from sklearn.linear_model import LogisticRegression


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="NCB Field Companion",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ NCB FIELD COMPANION")
st.caption("AI Presumptive Drug Identification Tool")


# ============================================================
# SESSION STATE
# ============================================================

if "spoken" not in st.session_state:
    st.session_state.spoken = False


# ============================================================
# LOAD JSON DATABASE
# ============================================================

try:
    with open(
        "reagents.json",
        "r",
        encoding="utf-8"
    ) as f:
        reagents_json = json.load(f)

except FileNotFoundError:

    reagents_json = {}

    st.warning(
        "reagents.json not found. "
        "The CSV-based ML model will still work."
    )


# ============================================================
# LOAD CSV DATABASE
# ============================================================

CSV_FILE = "drug_reagents.csv"


@st.cache_data
def load_reagent_csv():

    df = pd.read_csv(CSV_FILE)

    required_columns = [
        "reagent",
        "substance",
        "color",
        "hex_code",
        "ndps_section"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "Missing columns in drug_reagents.csv: "
            + ", ".join(missing)
        )

    return df


try:

    df_reagents = load_reagent_csv()

except Exception as e:

    st.error(
        f"Could not load drug_reagents.csv: {e}"
    )

    st.stop()


# ============================================================
# HEX → LAB
# ============================================================

def hex_to_lab(hex_code):

    hex_code = str(
        hex_code
    ).strip()

    if not hex_code.startswith("#"):
        hex_code = "#" + hex_code

    rgb = ImageColor.getrgb(
        hex_code
    )

    r, g, b = rgb

    bgr = np.uint8(
        [[[b, g, r]]]
    )

    lab = cv2.cvtColor(
        bgr,
        cv2.COLOR_BGR2LAB
    )

    return lab[0, 0].astype(float)


# Create LAB columns from CSV HEX values

df_reagents["lab"] = (
    df_reagents["hex_code"]
    .apply(hex_to_lab)
)

df_reagents["L"] = (
    df_reagents["lab"]
    .apply(lambda x: x[0])
)

df_reagents["A"] = (
    df_reagents["lab"]
    .apply(lambda x: x[1])
)

df_reagents["B"] = (
    df_reagents["lab"]
    .apply(lambda x: x[2])
)


# ============================================================
# PREPARE MACHINE LEARNING DATA
# ============================================================

X_base = df_reagents[
    ["L", "A", "B"]
].values.astype(float)

y_base = df_reagents[
    "substance"
].astype(str).values


# ============================================================
# SYNTHETIC LAB SAMPLES
# ============================================================

rng = np.random.default_rng(42)

X_train = []
y_train = []


for lab_value, substance in zip(
    X_base,
    y_base
):

    # Original sample
    X_train.append(lab_value)
    y_train.append(substance)

    # Synthetic samples around original colour
    for _ in range(100):

        noise = rng.normal(
            loc=0,
            scale=[5.0, 5.0, 5.0],
            size=3
        )

        new_lab = (
            lab_value + noise
        )

        new_lab[0] = np.clip(
            new_lab[0],
            0,
            255
        )

        new_lab[1] = np.clip(
            new_lab[1],
            0,
            255
        )

        new_lab[2] = np.clip(
            new_lab[2],
            0,
            255
        )

        X_train.append(
            new_lab
        )

        y_train.append(
            substance
        )


X_train = np.asarray(
    X_train,
    dtype=float
)

y_train = np.asarray(
    y_train
)


# ============================================================
# TRAIN LOGISTIC REGRESSION
# ============================================================

@st.cache_resource
def train_model(X, y):

    model = LogisticRegression(
        max_iter=2000,
        random_state=42
    )

    model.fit(
        X,
        y
    )

    return model


try:

    logistic_model = train_model(
        X_train,
        y_train
    )

except Exception as e:

    st.error(
        f"Could not train Logistic Regression: {e}"
    )

    st.stop()


# ============================================================
# RGB → LAB
# ============================================================

def rgb_to_lab(rgb):

    rgb_array = np.uint8(
        [[rgb]]
    )

    lab = cv2.cvtColor(
        rgb_array,
        cv2.COLOR_RGB2LAB
    )

    return lab[0][0]


# ============================================================
# COLOR DISTANCE
# ============================================================

def color_distance(
    lab1,
    lab2
):

    return np.linalg.norm(
        np.asarray(
            lab1,
            dtype=float
        )
        -
        np.asarray(
            lab2,
            dtype=float
        )
    )


# ============================================================
# ML PREDICTION
# ============================================================

def predict_drug(lab_value):

    lab_value = np.asarray(
        lab_value,
        dtype=float
    ).reshape(
        1,
        -1
    )

    prediction = (
        logistic_model
        .predict(
            lab_value
        )[0]
    )

    probabilities = (
        logistic_model
        .predict_proba(
            lab_value
        )[0]
    )

    confidence = (
        float(
            np.max(
                probabilities
            )
        )
        * 100
    )

    return (
        prediction,
        confidence
    )


# ============================================================
# CSV INFORMATION
# ============================================================

def get_csv_information(
    substance
):

    matches = df_reagents[
        df_reagents[
            "substance"
        ].astype(str)
        ==
        str(substance)
    ]

    if matches.empty:
        return None

    return matches.iloc[0].to_dict()


# ============================================================
# JSON INFORMATION
# ============================================================

def get_json_information(
    reagent_name,
    substance
):

    if not isinstance(
        reagents_json,
        dict
    ):
        return None

    for key, item in reagents_json.items():

        if not isinstance(
            item,
            dict
        ):
            continue

        json_reagent = str(
            item.get(
                "reagent",
                ""
            )
        ).strip()

        json_drug = str(
            item.get(
                "target_compound",
                item.get(
                    "drug",
                    ""
                )
            )
        ).strip()

        if (
            json_reagent.lower()
            ==
            str(
                reagent_name
            ).lower()
            and
            json_drug.lower()
            ==
            str(
                substance
            ).lower()
        ):

            return item

    return None


# ============================================================
# TEXT TO SPEECH
# ============================================================

def talk_back(text):

    if st.session_state.spoken:
        return

    try:

        engine = pyttsx3.init()

        engine.say(
            text
        )

        engine.runAndWait()

        engine.stop()

        st.session_state.spoken = True

    except Exception:

        pass


# ============================================================
# PDF REPORT
# ============================================================

def generate_pdf(
    officer,
    case,
    drug,
    confidence,
    rgb,
    lab,
    image,
    reagent=None,
    ndps_section=None
):

    tz = pytz.timezone(
        "Asia/Kolkata"
    )

    now = datetime.now(
        tz
    ).strftime(
        "%d-%m-%Y %H:%M:%S"
    )

    report_hash = hashlib.sha256(
        (
            f"{officer}"
            f"{case}"
            f"{drug}"
            f"{confidence}"
            f"{rgb}"
            f"{lab}"
            f"{now}"
        ).encode()
    ).hexdigest()

    pdf_path = (
        tempfile
        .NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        )
        .name
    )

    doc = SimpleDocTemplate(
        pdf_path
    )

    styles = (
        getSampleStyleSheet()
    )

    story = []

    story.append(
        Paragraph(
            "<b>NCB FIELD COMPANION REPORT</b>",
            styles["Title"]
        )
    )

    story.append(
        Paragraph(
            f"Officer ID: {officer}",
            styles["BodyText"]
        )
    )

    story.append(
        Paragraph(
            f"Case Ref: {case}",
            styles["BodyText"]
        )
    )

    story.append(
        Paragraph(
            f"Time (IST): {now}",
            styles["BodyText"]
        )
    )

    story.append(
        Paragraph(
            f"Suspected Drug: "
            f"<b>{drug}</b>",
            styles["BodyText"]
        )
    )

    story.append(
        Paragraph(
            f"Confidence: "
            f"{confidence:.1f}%",
            styles["BodyText"]
        )
    )

    if reagent:

        story.append(
            Paragraph(
                f"Reagent: {reagent}",
                styles["BodyText"]
            )
        )

    if ndps_section:

        story.append(
            Paragraph(
                f"NDPS Section: "
                f"{ndps_section}",
                styles["BodyText"]
            )
        )

    story.append(
        Paragraph(
            f"RGB: {rgb}",
            styles["BodyText"]
        )
    )

    story.append(
        Paragraph(
            f"LAB: {lab}",
            styles["BodyText"]
        )
    )

    story.append(
        Paragraph(
            "<b>NOTE:</b> This is a "
            "presumptive screening result "
            "and requires laboratory "
            "confirmation.",
            styles["BodyText"]
        )
    )

    story.append(
        Paragraph(
            f"SHA256 Hash: {report_hash}",
            styles["BodyText"]
        )
    )

    img_path = (
        tempfile
        .NamedTemporaryFile(
            delete=False,
            suffix=".png"
        )
        .name
    )

    cv2.imwrite(
        img_path,
        cv2.cvtColor(
            image,
            cv2.COLOR_RGB2BGR
        )
    )

    story.append(
        Image(
            img_path,
            width=3 * inch,
            height=3 * inch
        )
    )

    doc.build(
        story
    )

    with open(
        pdf_path,
        "rb"
    ) as f:

        pdf_data = f.read()

    try:

        os.remove(
            pdf_path
        )

        os.remove(
            img_path
        )

    except Exception:

        pass

    return pdf_data


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "👮 Officer Details"
)

officer_id = (
    st.sidebar.text_input(
        "Officer ID"
    )
)

case_ref = (
    st.sidebar.text_input(
        "Case Reference"
    )
)

brightness = (
    st.sidebar.slider(
        "Brightness",
        -50,
        50,
        0
    )
)


# ============================================================
# AI MODEL INFORMATION
# ============================================================

with st.sidebar.expander(
    "🤖 AI Model Information"
):

    st.write(
        "Model: Logistic Regression"
    )

    st.write(
        "Training source: "
        "drug_reagents.csv"
    )

    st.write(
        f"Training substances: "
        f"{df_reagents['substance'].nunique()}"
    )

    st.write(
        f"CSV records: "
        f"{len(df_reagents)}"
    )

    st.caption(
        "LAB colour features are "
        "generated from CSV HEX values."
    )


# ============================================================
# FLASH CONTROL
# ============================================================

st.subheader(
    "📷 Camera Controls"
)

flash_on = st.toggle(
    "🔦 Flash ON/OFF",
    value=False,
    help=(
        "Attempts to enable the "
        "device camera torch when "
        "supported by the browser."
    )
)

if flash_on:

    st.success(
        "🔦 Flash requested: ON"
    )

else:

    st.info(
        "🔦 Flash: OFF"
    )


# ============================================================
# BROWSER TORCH CONTROL
# ============================================================

components.html(
    f"""
    <script>

    (async function() {{

        const flashEnabled =
            {str(flash_on).lower()};

        try {{

            if (
                !navigator.mediaDevices ||
                !navigator.mediaDevices.getUserMedia
            ) {{

                console.log(
                    "Camera API unavailable."
                );

                return;
            }}

            const stream =
                await navigator.mediaDevices
                .getUserMedia({{
                    video: {{
                        facingMode: {{
                            ideal: "environment"
                        }}
                    }}
                }});

            const tracks =
                stream.getVideoTracks();

            if (
                tracks.length === 0
            ) {{

                console.log(
                    "No camera track available."
                );

                return;
            }}

            const track =
                tracks[0];

            const capabilities =
                track.getCapabilities
                ? track.getCapabilities()
                : {{}};

            if (
                !capabilities.torch
            ) {{

                console.log(
                    "Torch not supported."
                );

                return;
            }}

            await track.applyConstraints({{
                advanced: [
                    {{
                        torch:
                            flashEnabled
                    }}
                ]
            }});

            console.log(
                flashEnabled
                ? "Torch ON"
                : "Torch OFF"
            );

        }}
        catch (error) {{

            console.log(
                "Torch error:",
                error
            );

        }}

    }})();

    </script>
    """,
    height=0
)


# ============================================================
# CAMERA
# ============================================================

photo = st.camera_input(
    "📷 Capture Reagent Test"
)


# ============================================================
# IMAGE ANALYSIS
# ============================================================

if photo is not None:

    st.session_state.spoken = False

    file_bytes = np.asarray(
        bytearray(
            photo.read()
        ),
        dtype=np.uint8
    )

    img = cv2.imdecode(
        file_bytes,
        cv2.IMREAD_COLOR
    )

    if img is None:

        st.error(
            "Unable to read the "
            "captured image."
        )

        st.stop()

    img = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2RGB
    )


    # ========================================================
    # BRIGHTNESS
    # ========================================================

    img = np.clip(
        img.astype(np.int16)
        + brightness,
        0,
        255
    ).astype(
        np.uint8
    )


    # ========================================================
    # CENTER ROI
    # ========================================================

    h, w, _ = img.shape

    roi_size = 40

    y1 = max(
        0,
        h // 2
        -
        roi_size // 2
    )

    y2 = min(
        h,
        h // 2
        +
        roi_size // 2
    )

    x1 = max(
        0,
        w // 2
        -
        roi_size // 2
    )

    x2 = min(
        w,
        w // 2
        +
        roi_size // 2
    )

    roi = img[
        y1:y2,
        x1:x2
    ]


    # ========================================================
    # RGB + LAB
    # ========================================================

    avg_rgb = (
        roi
        .mean(
            axis=(0, 1)
        )
        .astype(int)
        .tolist()
    )

    avg_lab = rgb_to_lab(
        avg_rgb
    )


    # ========================================================
    # DISPLAY IMAGE
    # ========================================================

    st.image(
        img,
        caption="Captured Image",
        use_container_width=True
    )

    st.image(
        roi,
        caption="40 × 40 Analysis ROI",
        width=200
    )


    col1, col2 = st.columns(2)

    with col1:

        st.success(
            f"Detected RGB: "
            f"{avg_rgb}"
        )

    with col2:

        st.info(
            f"LAB Value: "
            f"{avg_lab.tolist()}"
        )


    # ========================================================
    # AI PREDICTION
    # ========================================================

    try:

        predicted_drug, confidence = (
            predict_drug(
                avg_lab
            )
        )

    except Exception as e:

        st.error(
            f"Prediction failed: {e}"
        )

        st.stop()


    # ========================================================
    # CSV INFORMATION
    # ========================================================

    csv_info = (
        get_csv_information(
            predicted_drug
        )
    )


    # ========================================================
    # RESULT
    # ========================================================

    st.divider()

    st.subheader(
        "🧪 AI Analysis Result"
    )


    if confidence >= 70:

        drug = predicted_drug

        st.success(
            f"🧪 Suspected Drug: "
            f"{drug}"
        )

        st.metric(
            "Logistic Regression Confidence",
            f"{confidence:.1f}%"
        )


    elif confidence >= 40:

        drug = predicted_drug

        st.warning(
            f"⚠️ Low-confidence "
            f"possible match: "
            f"{drug}"
        )

        st.metric(
            "Confidence",
            f"{confidence:.1f}%"
        )


    else:

        drug = (
            "Inconclusive — "
            "Laboratory confirmation "
            "required"
        )

        st.warning(
            drug
        )

        st.metric(
            "Confidence",
            f"{confidence:.1f}%"
        )


    # ========================================================
    # DATABASE INFORMATION (CONTINUED)
    # ========================================================
    if csv_info is not None:
        st.subheader("📋 Reagent Database Information")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Reagent:** {csv_info['reagent']}")
            st.write(f"**Target Substance:** {csv_info['substance']}")
        with col2:
            st.write(f"**NDPS Provision:** {csv_info['ndps_section']}")
            st.write(f"**Reference Color:** {csv_info['color']}")

    # ========================================================
    # WEB-BASED TALK BACK (Works on Android Chrome)
    # ========================================================
    # We use JavaScript because the server cannot "speak" to your phone
    if confidence >= 40:
        speech_text = f"Analysis complete. The detected color is {csv_info['color'] if csv_info else 'Unknown'}. Statistical confidence of {predicted_drug} is {confidence:.0f} percent."
    else:
        speech_text = "Analysis inconclusive. No high confidence drug match found."

    components.html(f"""
        <script>
        window.speechSynthesis.cancel(); 
        var msg = new SpeechSynthesisUtterance("{speech_text}");
        msg.lang = 'en-IN';
        msg.rate = 0.9;
        window.speechSynthesis.speak(msg);
        </script>
    """, height=0)

    # ========================================================
    # PDF REPORT GENERATION
    # ========================================================
    st.divider()
    st.subheader("📄 Documentary Evidence")

    if not officer_id or not case_ref:
        st.warning("⚠️ Please enter Officer ID and Case Reference in the sidebar to generate a valid report.")
    else:
        # Generate the PDF in memory
        pdf_data = generate_pdf(
            officer=officer_id,
            case=case_ref,
            drug=drug,
            confidence=confidence,
            rgb=avg_rgb,
            lab=avg_lab.tolist(),
            image=img,
            reagent=csv_info['reagent'] if csv_info else "N/A",
            ndps_section=csv_info['ndps_section'] if csv_info else "N/A"
        )

        st.download_button(
            label="📥 Download Signed Forensic Report (PDF)",
            data=pdf_data,
            file_name=f"NCB_Report_{case_ref.replace('/', '_')}.pdf",
            mime="application/pdf"
        )

# ============================================================
# FOOTER
# ============================================================
st.sidebar.divider()
st.sidebar.caption("© 2024 NCB Field Companion | SIH Problem 26231")
st.sidebar.write(f"System Time: {get_india_time()}")

    
    
