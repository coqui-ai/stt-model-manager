"""Server hosting the STT UI"""
import json
import logging
import os
import socket
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from engineio.payload import Payload
from flask import Flask, Response, redirect, render_template, request, session, url_for
from flask_cors import CORS
from flask_socketio import Namespace, SocketIO, emit
from stt import Model
from webrtcvad import Vad
from werkzeug.serving import is_running_from_reloader

from .modelmanager import ModelManager

Payload.max_decode_packets = 10000
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app)

VAD = Vad(3)  # Very aggressive
SILENCE_THRESHOLD = timedelta(milliseconds=200)

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
        model_zoo_url=f"http://localhost:8000/models?callback_url=http://{host}:{port}/install_model",
        installed_models=list(app.config["MODEL_MANAGER"].list_models()),
    )


@app.route("/install_model", methods=["POST"])
def install_model():
    model_card = json.loads(request.data)
    print(f"Install model got data: {json.dumps(model_card)}")
    install_id = app.config["MODEL_MANAGER"].download_model(model_card)
    return redirect(url_for("model_install_page", install_id=install_id))


@socketio.on("start")
def on_connect(model_name):
    print(f"Starting session for model {model_name}")
    model_card = app.config["MODEL_MANAGER"].models_dict()[model_name]
    print(f"Creating model instance from {model_card.acoustic_path}")
    model_instance = Model(str(model_card.acoustic_path))
    if model_card.scorer_path:
        print(f"Enabling external scorer from {model_card.scorer_path}")
        model_instance.enableExternalScorer(model_card.scorer_path)

    session[request.sid] = TranscriptionInstance(request.sid, model_instance)


@socketio.on("stream-data")
def on_stream_data(data):
    instance = session[request.sid]
    instance.process_data(data)


@socketio.on("stream-reset")
def on_stream_reset():
    instance = session[request.sid]
    instance.stream_reset()


@socketio.on("stream-end")
def on_stream_end():
    instance = session[request.sid]
    instance.stream_end()


class TranscriptionInstance:
    def __init__(self, session_id: str, model_instance: Model):
        self.sid = session_id
        self.model = model_instance
        self.recorded_chunks = 0
        self.silence_start = None
        self.silence_buffers: deque = self.reset_silence_buffers()
        self.stream = self.model.createStream()

    def reset_silence_buffers(self) -> deque:
        return deque(maxlen=3)

    def process_data(self, data):
        if VAD.is_speech(data, 16000):
            self.process_voice(data)
        else:
            self.process_silence(data)

    def stream_reset(self):
        print(f"[{self.sid}:reset]")
        self.stream.finishStream()  # ignore results
        self.recorded_chunks = 0
        self.silence_start = None

    def process_voice(self, data):
        data = np.frombuffer(data, np.int16)

        self.silence_start = None
        if self.recorded_chunks == 0:
            print(f"\n[{self.sid}:start]", end="", flush=True)  # recording started
        else:
            print("=", end="", flush=True)  # still recording

        self.recorded_chunks += 1
        data_with_silence = self.add_buffered_silence(data)
        self.silence_buffers = self.reset_silence_buffers()
        self.stream.feedAudioContent(data_with_silence)

    def add_buffered_silence(self, data):
        return np.concatenate((*self.silence_buffers, data))

    def process_silence(self, data):
        data = np.frombuffer(data, np.int16)

        if self.recorded_chunks > 0:  # recording is on
            print("-", end="", flush=True)  # silence detected while recording

            self.stream.feedAudioContent(data)

            if self.silence_start is None:
                self.silence_start = datetime.now()
            else:
                now = datetime.now()
                if now - self.silence_start > SILENCE_THRESHOLD:
                    self.silence_start = None
                    print(f"[{self.sid}:end]")
                    result = self.stream.finishStream()
                    self.stream = self.model.createStream()
                    self.silence_buffers = self.reset_silence_buffers()
                    if result:
                        print(f"Recognized text: {result} (len={len(result)})")
                        emit("recognize", {"text": result})
        else:
            print(".", end="", flush=True)  # silence detected while not recording
            # VAD has a tendency to cut the first bit of audio data from the
            # start of a recording so keep a buffer of that first bit of audio
            # and reinsert it to the beginning of the recording.
            self.silence_buffers.append(data)


@app.route("/install_model/<string:install_id>")
def model_install_page(install_id: str):
    print(app.config["MODEL_MANAGER"].install_tasks)
    task = app.config["MODEL_MANAGER"].get_install_task_state(install_id)
    return render_template(
        "model_install.html",
        install_id=install_id,
        model_name=task.model_card.name,
        start_progress=task.total_progress,
    )


@app.route("/install_model/<string:install_id>/progress")
def get_progress_for_install(install_id: str):
    print(f"Got request for progress updates for model install {install_id}")
    if not app.config["MODEL_MANAGER"].has_install_task_state(install_id):
        return ("Not found", 404)

    def generate():
        progress = (
            app.config["MODEL_MANAGER"]
            .get_install_task_state(install_id)
            .total_progress
        )
        while progress < 100:
            print(f"Progress: {progress}")
            yield f"data:{progress}\n\n"
            time.sleep(1)
            progress = (
                app.config["MODEL_MANAGER"]
                .get_install_task_state(install_id)
                .total_progress
            )
        yield "data:100\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/transcribe/<string:model_name>")
def transcribe_with_model(model_name: str):
    if model_name not in app.config["MODEL_MANAGER"].models_dict():
        return (404, "Model not found")

    return render_template("transcribe.html", model_name=model_name)


@app.before_first_request
def on_server_init():
    print(f"running from reloader = {is_running_from_reloader()}")


def build_app(host: str = "127.0.0.1", port: Optional[int] = None):
    if not is_debug():
        werkzeug_log = logging.getLogger("werkzeug")
        werkzeug_log.setLevel(logging.ERROR)

    # Get available but known port if no explicit port was specified
    if not port:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]
        sock.close()

    app.config["MODEL_MANAGER"] = ModelManager()
    app.config["SERVER_HOST"] = host
    app.config["SERVER_PORT"] = port
    app.secret_key = b"aeiou"
    _server_initialized.set()
    return app


def start_app(app: Flask):
    host, port = get_server_hostport()
    socketio.run(
        app,
        host=host,
        port=port,
        debug=is_debug(),
        use_reloader=is_debug(),  # Disable reloader to avoid problems when running the server from a thread
    )
