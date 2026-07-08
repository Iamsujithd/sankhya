import time
import streamlit as st
from streamlit_lottie import st_lottie
from util import load_lottie, stream_data, welcome_message, introduction_message
from prediction_model import prediction_model_pipeline
from cluster_model import cluster_model_pipeline
from regression_model import regression_model_pipeline
from visualization import data_visualization
from src.util import read_file_from_streamlit
from copilot import run_copilot

st.set_page_config(page_title="Sankhya: AI Data Analyst", page_icon=":rocket:", layout="wide")

# TITLE SECTION
with st.container():
    st.subheader("Hello there 👋")
    st.title("Welcome to Sankhya!")
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
    if st.session_state.initialized:
        st.session_state.welcome_message = welcome_message()
        st.write(stream_data(st.session_state.welcome_message))
        time.sleep(0.5)
        st.write("[GitHub Repository >](https://github.com/Iamsujithd/sankhya)")
        st.session_state.initialized = False
    else:
        st.write(st.session_state.welcome_message)
        st.write("[GitHub Repository >](https://github.com/Iamsujithd/sankhya)")

# INTRO SECTION
with st.container():
    st.divider()
    if 'lottie' not in st.session_state:
        st.session_state.lottie_url1, st.session_state.lottie_url2 = load_lottie()
        st.session_state.lottie = True

    left_column_r1, right_column_r1 = st.columns([6, 4])
    with left_column_r1:
        st.header("What can Sankhya do?")
        st.write(introduction_message()[0])
    with right_column_r1:
        if st.session_state.lottie:
            st_lottie(st.session_state.lottie_url1, height=280, key="animation1")

    left_column_r2, _, right_column_r2 = st.columns([6, 1, 5])
    with left_column_r2:
        if st.session_state.lottie:
            st_lottie(st.session_state.lottie_url2, height=200, key="animation2")
    with right_column_r2:
        st.header("Simple to Use")
        st.write(introduction_message()[1])

# MAIN SECTION
with st.container():
    st.divider()
    st.header("Let's Get Started")
    left_column, right_column = st.columns([6, 4])
    
    with right_column:
        PROVIDER = st.selectbox(
            'Select AI Provider',
            ('Groq (Ultra Fast)', 'OpenAI')
        )
        
        if PROVIDER == 'Groq (Ultra Fast)':
            SELECTED_MODEL = st.selectbox(
                'Select Model',
                ('llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768')
            )
        else:
            SELECTED_MODEL = st.selectbox(
                'Select Model',
                ('GPT-4-Turbo', 'GPT-3.5-Turbo')
            )

        MODE = st.selectbox(
            'Select proper data analysis mode',
            ('AI Data Copilot (Chat with Data)', 'Predictive Classification', 'Clustering Model', 'Regression Model', 'Data Visualization')
        )
        
        st.write(f'Provider: :green[{PROVIDER}]')
        st.write(f'Model: :green[{SELECTED_MODEL}]')
        st.write(f'Mode: :green[{MODE}]')
        
    with left_column:
        import os
        default_key = os.environ.get("GROQ_API_KEY", "")
        if PROVIDER == 'Groq (Ultra Fast)' and not default_key:
            # Check if there is a key entered or stored
            default_key = ""
            
        API_KEY = st.text_input(
            "Your API Key:",
            value=default_key,
            type="password",
            placeholder="gsk_..." if PROVIDER == 'Groq (Ultra Fast)' else "sk_..."
        )
        uploaded_file = st.file_uploader("Choose a data file. Your data won't be stored!", accept_multiple_files=False, type=['csv', 'json', 'xls', 'xlsx'])
        if uploaded_file:
            if uploaded_file.getvalue():
                uploaded_file.seek(0)
                st.session_state.DF_uploaded = read_file_from_streamlit(uploaded_file)
                st.session_state.is_file_empty = False
            else:
                st.session_state.is_file_empty = True

    # Proceed Button
    is_proceed_enabled = uploaded_file is not None and API_KEY != "" or uploaded_file is not None and MODE == "Data Visualization"

    # Initialize the 'button_clicked' state
    if 'button_clicked' not in st.session_state:
        st.session_state.button_clicked = False
    if st.button('Start Analysis', disabled=(not is_proceed_enabled) or st.session_state.button_clicked, type="primary"):
        st.session_state.button_clicked = True
    if "is_file_empty" in st.session_state and st.session_state.is_file_empty:
        st.caption('Your data file is empty!')

    # Start Analysis
    if st.session_state.button_clicked:
        with st.container():
            if "DF_uploaded" not in st.session_state:
                st.error("File is empty!")
            else:
                if MODE == 'AI Data Copilot (Chat with Data)':
                    run_copilot(st.session_state.DF_uploaded, API_KEY, SELECTED_MODEL)
                elif MODE == 'Predictive Classification':
                    prediction_model_pipeline(st.session_state.DF_uploaded, API_KEY, SELECTED_MODEL)
                elif MODE == 'Clustering Model':
                    cluster_model_pipeline(st.session_state.DF_uploaded, API_KEY, SELECTED_MODEL)
                elif MODE == 'Regression Model':
                    regression_model_pipeline(st.session_state.DF_uploaded, API_KEY, SELECTED_MODEL)
                elif MODE == 'Data Visualization':
                    data_visualization(st.session_state.DF_uploaded)