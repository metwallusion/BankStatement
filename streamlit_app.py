import streamlit as st
from io import BytesIO
import pandas as pd
from parse_bank_statement import parse_pdf

st.title("Bank Statement PDF to CSV")
st.subheader("Upload a PDF Bank Statement file and download it as a CSV easily")

uploaded = st.file_uploader("Upload PDF", type="pdf")
if uploaded:
    data = uploaded.read()
    pdf_bytes = BytesIO(data)
    rows = parse_pdf(pdf_bytes)
    df = pd.DataFrame(rows)
    st.dataframe(df)
    csv_data = df.to_csv(index=False)
    st.download_button("Download CSV", csv_data, file_name="statement.csv", mime="text/csv")
    
    
st.caption("Developed by Mito (Only for internal usage of AOA): https://www.linkedin.com/in/ahmed-m%C3%A9twalli/")
