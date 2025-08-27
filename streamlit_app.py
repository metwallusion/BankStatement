import streamlit as st
from pathlib import Path
import pandas as pd
from parse_bank_statement import parse_pdf

st.title("Bank Statement PDF to CSV")
st.subheader(
    "Upload one or more PDF bank statements and download each as a CSV file"
)
uploads = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)

if uploads:
    for uploaded in uploads:
        with st.spinner(f"Processing {uploaded.name}. Please wait..."):
            uploaded.seek(0)
            rows = parse_pdf(uploaded)
            df = pd.DataFrame(rows)
            df.insert(0, "Selected", False)

        with st.expander(uploaded.name):
            state_key = f"df_{uploaded.name}"
            if state_key not in st.session_state:
                st.session_state[state_key] = df

            df_state = st.session_state[state_key]

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Select All", key=f"select_all_{uploaded.name}"):
                    df_state["Selected"] = True
            with col2:
                if st.button("Unselect All", key=f"unselect_all_{uploaded.name}"):
                    df_state["Selected"] = False
            with col3:
                if st.button("Flip Signs", key=f"flip_{uploaded.name}"):
                    df_state.loc[df_state["Selected"], "Amount"] *= -1

            st.session_state[state_key] = df_state

            df_state = st.data_editor(df_state, key=f"editor_{uploaded.name}")
            st.session_state[state_key] = df_state

            csv_name = f"{Path(uploaded.name).stem}.csv"
            csv_data = df_state.drop(columns=["Selected"]).to_csv(index=False)
            st.download_button(
                f"Download {csv_name}",
                csv_data,
                file_name=csv_name,
                mime="text/csv",
            )
    
st.caption("Developed by Mito (Only for internal usage of AOA): https://www.linkedin.com/in/ahmed-m%C3%A9twalli/")
