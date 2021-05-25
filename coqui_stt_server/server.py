"""Server hosting the STT UI"""
import json
import logging
import os
import socket
import threading
from typing import Optional, Tuple

from flask import Flask, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["https://reub.in", "https://coqui.ai"])

_server_initialized = threading.Event()


def is_debug() -> bool:
    return "COQUI_STT_SERVER_DEBUG" in os.environ


def get_server_hostport() -> Tuple[str, int]:
    _server_initialized.wait()
    assert (
        "SERVER_HOST" in app.config
    ), "server not initialized (should never happen due to wait above)"
    assert (
        "SERVER_PORT" in app.config
    ), "server not initialized (should never happen due to wait above)"
    return (app.config["SERVER_HOST"], app.config["SERVER_PORT"])


@app.route("/")
def index():
    host, port = get_server_hostport()
    return render_template(
        "index.html",
        model_zoo_callback_url=f"http://{host}:{port}/install_model",
    )


@app.route("/install_model", methods=["POST"])
def install_model():
    print(f"Install model got data: <pre>{json.dumps(request.get_json())}</pre>")
    return ("", 204)


def start_app(host: str = "127.0.0.1", port: Optional[int] = None):
    if not is_debug():
        werkzeug_log = logging.getLogger("werkzeug")
        werkzeug_log.setLevel(logging.ERROR)

    # Get available but known port if no explicit port was specified
    if not port:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]
        sock.close()

    app.config["SERVER_HOST"] = host
    app.config["SERVER_PORT"] = port
    _server_initialized.set()

    app.run(
        host=host,
        port=port,
        debug=is_debug(),
        use_reloader=False,  # Disable reloader to avoid problems when running the server from a thread
    )
