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

        with st.expander(uploaded.name):
            st.dataframe(df)
            csv_name = f"{Path(uploaded.name).stem}.csv"
            csv_data = df.to_csv(index=False)
            st.download_button(
                f"Download {csv_name}",
                csv_data,
                file_name=csv_name,
                mime="text/csv",
            )
    
st.caption("Developed by Mito (Only for internal usage of AOA): https://www.linkedin.com/in/ahmed-m%C3%A9twalli/")
