"""Server hosting the STT UI"""
import json
import logging
import os
import sys
import threading
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from queue import SimpleQueue
from typing import Optional, Tuple

import numpy as np
from engineio.payload import Payload
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS
from flask_socketio import SocketIO
from stt import Model
from webrtcvad import Vad

from .modelmanager import ModelCard, ModelManager

Payload.max_decode_packets = 10000
app = Flask(__name__)
CORS(app, origins=["https://coqui.ai"])
socketio = SocketIO(app)

VAD = Vad(3)  # Very aggressive
SILENCE_THRESHOLD = timedelta(milliseconds=200)

_server_initialized = threading.Event()


def is_debug() -> bool:
    return "COQUI_STT_MODEL_MANAGER_DEBUG" in os.environ or "--debug" in sys.argv


def open_folder(path: Path):
    assert path.is_dir()
    assert path.is_absolute()
    webbrowser.open(f"file://{path}")


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
    current_installs = [
        task.to_dict()
        for task in app.config["MODEL_MANAGER"].install_tasks.values()
        if task.total_progress < 100
    ]
    print(f"Current installs: {current_installs}")
    return render_template(
        "index.html",
        model_zoo_url=f"https://coqui.ai/models?callback_url=http://{host}:{port}/install_model&prefer_tflite=1",
        installed_models=list(app.config["MODEL_MANAGER"].list_models()),
        models_being_installed=current_installs,
    )


@app.route("/install_model", methods=["POST"])
def install_model():
    print(f"Install model got data: {request.data}")
    model_card = json.loads(request.data)
    app.config["MODEL_MANAGER"].download_model(model_card)
    return redirect(url_for("index"))


@app.route("/show_model_files/<string:model_name>")
def show_model_files(model_name):
    if model_name not in app.config["MODEL_MANAGER"].models_dict():
        return (404, "Not found")

    model_card = app.config["MODEL_MANAGER"].models_dict()[model_name]
    open_folder(Path(model_card.acoustic_path).parent)
    return redirect(url_for("index"))


@socketio.on("start")
def on_connect(model_name):
    print(f"Starting session for model {model_name}")
    model_card = app.config["MODEL_MANAGER"].models_dict()[model_name]
    instance = TranscriptionInstance(request.sid, model_card)
    instance.start()
    session[request.sid] = instance


@socketio.on("stream-data")
def on_stream_data(data):
    instance = session[request.sid]
    instance.process_data(data)


@socketio.on("stream-reset")
def on_stream_reset():
    instance = session[request.sid]
    instance.stream_reset()


@socketio.on("stream-intermediate")
def on_stream_intermediate():
    instance = session[request.sid]
    instance.stream_intermediate()


def _reset_silence_buffers() -> deque:
    return deque(maxlen=3)


class TranscriptionInstance(threading.Thread):
    """Thread responsible for transcribing data for a single transcription instance
    (which corresponds to a SocketIO session - see `on_connect`).
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, session_id: str, model_card: ModelCard):
        super().__init__(daemon=True)
        self.sid = session_id
        self.model_card = model_card
        self.model = None
        self.stream = None
        self.recorded_chunks = 0
        self.silence_start = None
        self.silence_buffers: deque = _reset_silence_buffers()
        self.queue: SimpleQueue = SimpleQueue()

    def process_data(self, data):
        self.queue.put(("data", data))

    def _process_data(self, data):
        if VAD.is_speech(data, 16000):
            self._process_voice(data)
        else:
            self._process_silence(data)

    def stream_reset(self):
        self.queue.put(("reset", None))

    def _stream_reset(self):
        print(f"[{self.sid}:reset]")
        self.stream.finishStream()  # ignore results
        self.stream = self.model.createStream()
        self.recorded_chunks = 0
        self.silence_start = None

    def stream_intermediate(self):
        self.queue.put(("intermediate", None))

    def _stream_intermediate(self):
        result = self.stream.intermediateDecode()
        if result:
            socketio.emit("intermediate", {"text": result}, to=self.sid)

    def _process_voice(self, data):
        data = np.frombuffer(data, np.int16)

        self.silence_start = None
        if self.recorded_chunks == 0:
            print(f"\n[{self.sid}:start]", end="", flush=True)  # recording started
        else:
            print("=", end="", flush=True)  # still recording

        self.recorded_chunks += 1
        data_with_silence = self._add_buffered_silence(data)
        self.silence_buffers = _reset_silence_buffers()
        self.stream.feedAudioContent(data_with_silence)

    def _add_buffered_silence(self, data):
        return np.concatenate((*self.silence_buffers, data))

    def _process_silence(self, data):
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
                    self.silence_buffers = _reset_silence_buffers()
                    if result:
                        print(f"Recognized text: {result} (len={len(result)})")
                        socketio.emit("recognize", {"text": result}, to=self.sid)
        else:
            print(".", end="", flush=True)  # silence detected while not recording
            # VAD has a tendency to cut the first bit of audio data from the
            # start of a recording so keep a buffer of that first bit of audio
            # and reinsert it to the beginning of the recording.
            self.silence_buffers.append(data)

    def exit(self):
        self.queue.put(("exit", None))

    def run(self):
        print(f"Creating model instance from {self.model_card.acoustic_path}")
        self.model = Model(str(self.model_card.acoustic_path))
        if self.model_card.scorer_path:
            print(f"Enabling external scorer from {self.model_card.scorer_path}")
            self.model.enableExternalScorer(str(self.model_card.scorer_path))
        self.stream = self.model.createStream()

        while True:
            cmd, data = self.queue.get()
            if cmd == "exit":
                break

            if cmd == "data":
                self._process_data(data)
            elif cmd == "reset":
                self._stream_reset()
            elif cmd == "intermediate":
                self._stream_intermediate()


@app.route("/installs_progress")
def get_progress_for_install():
    tasks = [
        task.to_dict() for task in app.config["MODEL_MANAGER"].install_tasks.values()
    ]
    return jsonify(tasks)


@app.route("/transcribe/<string:model_name>")
def transcribe_with_model(model_name: str):
    if model_name not in app.config["MODEL_MANAGER"].models_dict():
        return (404, "Model not found")

    model_card = app.config["MODEL_MANAGER"].models_dict()[model_name]
    scorer_basename = ""
    if model_card.scorer_path:
        scorer_basename = Path(model_card.scorer_path).stem
    return render_template(
        "transcribe.html", model_card=model_card, scorer_basename=scorer_basename
    )


def build_app(
    host: str = "127.0.0.1",
    port: int = 38450,
    testing: bool = False,
    install_dir: Optional[Path] = None,
):
    if not is_debug():
        werkzeug_log = logging.getLogger("werkzeug")
        werkzeug_log.setLevel(logging.ERROR)

    if testing:
        app.config["TESTING"] = True

    app.config["MODEL_MANAGER"] = ModelManager(install_dir)
    app.config["SERVER_HOST"] = host
    app.config["SERVER_PORT"] = port
    app.secret_key = b"aeiou"
    _server_initialized.set()

    # Migrations
    app.config["MODEL_MANAGER"].maybe_upgrade_protobuf()

    return app


def start_app(app_instance: Flask):
    host, port = get_server_hostport()

    socketio.run(
        app_instance,
        host=host,
        port=port,
        debug=is_debug(),
        use_reloader=is_debug(),  # Disable reloader to avoid problems when running the server from a thread
    )
