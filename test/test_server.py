import json
import shutil
import sys
import tempfile
import time

import pytest

from coqui_stt_model_manager.server import app, build_app

# pytest forces us to redefine the `client` global function as a parameter of
# the test cases as that's how you request a fixture, so we disable this lint
# globally in this file.
# pylint: disable=redefined-outer-name


@pytest.fixture
def client():
    temp_install_dir = tempfile.mkdtemp()
    build_app(testing=True, install_dir=temp_install_dir)

    with app.test_client() as test_client:
        yield test_client

    if "--leave_test_artifacts_behind" not in sys.argv:
        shutil.rmtree(temp_install_dir)


def test_empty_db(client):
    response = client.get("/")
    response_str = response.data.decode("utf8")
    assert "Install a model from the Coqui STT Model zoo to get started" in response_str
    assert "0%" not in response_str


def test_install_model_start_transcription(client):
    test_model_params = dict(
        name="test_model",
        language="English",
        version="0.0.1",
        creator="reuben",
        acoustic="https://github.com/reuben/stt-model-manager/releases/download/v0.0.12/yesno.pbmm",
        scorer="https://github.com/reuben/stt-model-manager/releases/download/v0.0.12/yesno.scorer",
    )

    response = client.post(
        "/install_model",
        data=json.dumps(test_model_params),
        follow_redirects=True,
    )
    response_str = response.data.decode("utf8")
    assert "Install a new model from the Coqui STT Model Zoo" in response_str
    assert "0%..." in response_str

    print("Waiting for install...")
    while any(
        t.total_progress != 100
        for t in app.config["MODEL_MANAGER"].install_tasks.values()
    ):
        print(".", end="", flush=True)
        time.sleep(2)
    print("")

    time.sleep(1)

    response = client.get("/")
    response_str = response.data.decode("utf8")
    for key in ("name", "language", "version", "creator"):
        assert f"<td>{test_model_params[key]}</td>" in response_str

    # Test just basic rendering of transcribe page with model installed above
    # The actual transcription process will be tested with a SocketIO test client
    response = client.get(f"/transcribe/{test_model_params['name']}")
    assert response.status_code == 200
