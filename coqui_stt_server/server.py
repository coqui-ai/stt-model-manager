"""Server hosting the STT UI"""
import json
import logging
import os

from flask import Flask, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["https://reub.in", "https://coqui.ai"])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/install_model", methods=["POST"])
def install_model():
    print(f"Install model got data: <pre>{json.dumps(request.get_json())}</pre>")
    return ("", 204)


def start_app(host="0.0.0.0", port=12345):
    werkzeug_log = logging.getLogger("werkzeug")
    werkzeug_log.setLevel(logging.ERROR)
    # Disable reloader to avoid problems when running the server from a thread
    app.run(
        host=host,
        port=port,
        debug="COQUI_STT_SERVER_DEBUG" in os.environ,
        use_reloader=False,
    )
