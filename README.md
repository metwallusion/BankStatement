This repository contains tools to parse bank statement PDFs and export the
transaction data as CSV files. A Streamlit UI is included for easy use.

## Usage

1. **Install dependencies**
   ```sh
   ./install.sh
   ```
   This creates a Python virtual environment and installs the required
   packages.

2. **Run the web interface**
   ```sh
   source venv/bin/activate
   streamlit run streamlit_app.py
   ```
   Upload a PDF statement and download the generated CSV.

3. **Command line**
   ```sh
   python parse_bank_statement.py input.pdf output.csv
   ```
   Parses `input.pdf` and writes the transactions to `output.csv`.

## Standalone executables

To run the Streamlit app without installing Python, you can bundle it using
[PyInstaller](https://pyinstaller.org/). The provided `run_app.py` script
launches the Streamlit interface. Build a single-file binary on each target OS:

```sh
pip install pyinstaller
# Include Streamlit's static assets and the app source so the UI loads correctly
pyinstaller \
  --onefile \
  --copy-metadata streamlit \
  --collect-all streamlit \
  --add-data "streamlit_app.py:." \
  run_app.py
```

The launcher forces `STREAMLIT_GLOBAL_DEVELOPMENT_MODE=false` so the app
serves static assets and doesn't default to port `3000` when frozen. It also
loads Streamlit's config options before starting the server so `--server.port`
and the `PORT` environment variable are applied correctly.

On Windows replace the colon in `--add-data` with a semicolon.

The executable will be placed in the `dist` directory (`run_app.exe` on
Windows or `run_app` on macOS). Launching it will open the web page and allow
PDF upload and CSV download with no Python environment required.

By default the app listens on port `8501`. If that port is blocked, set the
`PORT` environment variable or pass `--server.port`:

```sh
PORT=8502 ./run_app        # or run_app.exe --server.port 8502 on Windows
```