import os
os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")

import sys
import multiprocessing
import tempfile
import pkgutil
from streamlit.web import bootstrap

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Force production mode so Streamlit doesn't use the Node dev server,
    # which would run on port 3000. This prevents PyInstaller builds from
    # mistakenly switching to development mode.
    script = os.path.join(os.path.dirname(__file__), "streamlit_app.py")
    if not os.path.exists(script):
        data = pkgutil.get_data(__name__, "streamlit_app.py")
        if data is None:
            raise FileNotFoundError("streamlit_app.py not bundled")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
        tmp.write(data)
        tmp.close()
        script = tmp.name
    # Allow a custom port via the PORT env var or --server.port flag.
    port = os.environ.get("PORT")
    args: list[str] = []
    flag_options: dict[str, str] = {}
    it = iter(sys.argv[1:])
    for arg in it:
        if arg == "--server.port":
            flag_options["server_port"] = next(it, None)
        elif arg.startswith("--server.port="):
            flag_options["server_port"] = arg.split("=", 1)[1]
        else:
            args.append(arg)

    if "server_port" not in flag_options and port:
        flag_options["server_port"] = port

    # Load config options (including server_port) before starting the server.
    bootstrap.load_config_options(flag_options)
    # Ensure production mode to avoid the Node dev server on port 3000.
    from streamlit import config
    config.set_option("global.developmentMode", False)

    # The second argument to `run` indicates if this is the "Hello" demo.
    # Pass False so Streamlit starts normally.
    bootstrap.run(script, False, args, flag_options)
