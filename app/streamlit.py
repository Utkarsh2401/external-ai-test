import streamlit as st
import logging
import os
import time
from PIL import Image
from datetime import datetime
from main import execute_streamlit, init_db, configurations, ConfigClass

logging.basicConfig(level=logging.INFO)

OUTPUT_DIR = "/app/outputs"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

init_db()

st.set_page_config(
    page_title="Visual Scene Design AI",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎨 Visual Scene Design AI")
st.write("Transform your text descriptions into stunning visual scenes and 3D models using AI.")

default_app_ids = [
    "c25dcd829d134ea98f5ae4dd311d13bc.node3.openfabric.network",
    "f0b5f319156c4819b9827000b17e511a.node3.openfabric.network"
]
configurations["super-user"] = ConfigClass(app_ids=default_app_ids)

st.header("Describe Your Scene")

if 'user_prompt' not in st.session_state:
    st.session_state.user_prompt = ""

user_prompt = st.text_area(
    "Enter your scene description",
    value=st.session_state.user_prompt,
    height=150
)
st.session_state.user_prompt = user_prompt

generate_button = st.button("🚀 Generate Scene")

if generate_button and user_prompt:
    progress_placeholder = st.empty()

    thinking_texts = [
        "Analyzing your imagination.",
        "Expanding the vision..",
        "Sketching the scene...",
        "Adding fine details....",
        "Finalizing the masterpiece....."
    ]
    
    for i in range(len(thinking_texts) * 2):
        progress_placeholder.info(thinking_texts[i % len(thinking_texts)])
        time.sleep(1)

    try:
        result = execute_streamlit(user_prompt)
        
        if result:
            progress_placeholder.empty()
            st.success("Scene generated successfully!")
            
            st.subheader("Expanded Description")
            st.info(result["expanded_prompt"])

            st.subheader("Generated Image")
            try:
                image = Image.open(result["image_path"])
                st.image(image, use_container_width=True)
            except Exception as e:
                st.error(f"Error loading image: {str(e)}")
            
            st.subheader("3D Model")
            if result.get("model_path") and os.path.exists(result["model_path"]):
                with open(result["model_path"], "rb") as file:
                    model_bytes = file.read()
                st.download_button(
                    label="Download 3D Model (GLB)",
                    data=model_bytes,
                    file_name=os.path.basename(result["model_path"]),
                    mime="application/octet-stream"
                )
                st.info("Use Blender or online viewers to open the 3D model.")
            else:
                st.warning("3D model not available.")
        else:
            progress_placeholder.error("Generation failed. Please try again.")
    except Exception as e:
        progress_placeholder.error(f"Error during generation: {str(e)}")
        logging.error(f"Generation error: {str(e)}", exc_info=True)
else:
    st.info("Enter a description above and click **Generate Scene** to create your masterpiece!")

st.markdown("---")
st.caption("Powered by Openfabric AI Services")
