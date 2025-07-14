#!/bin/sh
set -e
python3 -m venv venv
. venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "Run with: source venv/bin/activate && streamlit run streamlit_app.py"
