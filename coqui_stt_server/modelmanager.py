import json
import math
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread
from typing import Dict, Iterator, List, Optional, Tuple

import requests
from coqpit import Coqpit
from xdg import BaseDirectory as xdg


@dataclass
class ModelCard(Coqpit):  # pylint: disable=too-many-instance-attributes
    """Dataclass representation of a model card JSON"""

    name: str = field(metadata={"help": "name of this model"})
    language: str = field(metadata={"help": "language of this model"})
    version: str = field(metadata={"help": "version of this model"})
    creator: str = field(metadata={"help": "creator of this model"})
    acoustic: str = field(metadata={"help": "URL of acoustic model"})
    scorer: Optional[str] = field(default=None, metadata={"help": "URL of scorer"})
    installed: bool = field(
        default=False, metadata={"help": "whether this model is completely installed"}
    )
    acoustic_path: Optional[Path] = field(
        default=None, metadata={"help": "path to downloaded acoustic model"}
    )
    scorer_path: Optional[Path] = field(
        default=None, metadata={"help": "path to downloaded scorer, if available"}
    )


@dataclass
class ModelIndex(Coqpit):
    """Model index which gets persisted on disk by ModelManager."""

    models: List[ModelCard] = field(
        default_factory=lambda: [], metadata={"help": "list of installed models"}
    )


def _download_one(url: str, dest_path: Path):
    response = requests.get(url, stream=True)
    total_length = response.headers.get("Content-Length")

    with open(dest_path, "wb") as fout:
        if total_length is None:
            yield 0
            fout.write(response.content)
            yield 100
        else:
            total_bytes = int(total_length)
            done_bytes = 0
            for chunk in response.iter_content(chunk_size=8192):
                done_bytes += len(chunk)
                fout.write(chunk)
                done_pct = math.ceil((done_bytes / total_bytes) * 100)
                yield done_pct
            yield 100


class ModelInstallTask(Thread):  # pylint: disable=too-many-instance-attributes
    """Thread for downloading a model in the background and reporting progress"""

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        model_manager: "ModelManager",
        model_card: ModelCard,
        acoustic_url: str,
        acoustic_path: Path,
        scorer_url: Optional[str] = None,
        scorer_path: Optional[Path] = None,
    ):
        super().__init__()
        self.model_manager = model_manager
        self.model_card = model_card
        self.acoustic_url = acoustic_url
        self.acoustic_path = acoustic_path
        has_scorer_url = scorer_url is not None
        has_scorer_path = scorer_path is not None
        assert (
            has_scorer_url == has_scorer_path
        ), "scorer url and path must be specified (or skipped) together"
        self.has_scorer = has_scorer_url
        self.scorer_url = scorer_url
        self.scorer_path = scorer_path
        # Progress reporting
        self.total_steps = 2 if self.has_scorer else 1
        self.step = 0
        self.acoustic_progress = 0
        self.scorer_progress = 0 if self.has_scorer else 100

    @property
    def current_step(self):
        if self.step == 0:
            return "acoustic"
        if self.step == 1:
            return "scorer"
        if self.step == 2:
            return "complete"
        return "invalid"

    @property
    def total_progress(self):
        progress_pct = ((self.acoustic_progress + self.scorer_progress) / 200) * 100
        return math.ceil(progress_pct)

    def run(self):
        self.acoustic_path.parent.mkdir(parents=True, exist_ok=True)
        self.step = 0
        for progress in _download_one(self.acoustic_url, self.acoustic_path):
            self.acoustic_progress = progress

        if self.has_scorer:
            self.step = 1
            self.scorer_path.parent.mkdir(parents=True, exist_ok=True)
            for progress in _download_one(self.scorer_url, self.scorer_path):
                self.scorer_progress = progress

        self.model_manager.report_install_complete(
            self.model_card, self.acoustic_path, self.scorer_path
        )


class ModelManager:
    """Manage locally installed models.
    It provides an interface to list installed models and download/install a new
    model from the Coqui Model Zoo.
    """

    def __init__(self):
        self.install_dir = Path(xdg.save_data_path(Path("coqui") / "models"))
        self.model_index_path = self.install_dir / Path("models.json")
        if self.model_index_path.exists():
            self.read_index_from_disk()
        else:
            self.installed_models = ModelIndex()
            self.persist_index_to_disk()
        print(f"Installed models: {self.installed_models}")
        self.install_tasks = {}

    def read_index_from_disk(self):
        with open(self.model_index_path) as fin:
            self.installed_models = ModelIndex.new_from_dict(json.load(fin))

    def persist_index_to_disk(self):
        with open(self.model_index_path, "w") as fout:
            fout.write(self.installed_models.to_json())

    def list_models(self) -> List[ModelCard]:
        return self.installed_models.models

    def models_dict(self) -> Dict[str, ModelCard]:
        return {m.name: m for m in self.installed_models.models}

    def has_install_task_state(self, install_id: uuid.UUID):
        return str(install_id) in self.install_tasks

    def get_install_task_state(self, install_id: uuid.UUID):
        return self.install_tasks[str(install_id)]

    def set_install_task_state(self, install_id: uuid.UUID, state):
        self.install_tasks[str(install_id)] = state

    def list_install_task_states(self) -> Iterator[Tuple[str, int, str]]:
        for install_id, task in self.install_tasks.items():
            yield task.model_card.name, task.total_progress, str(install_id)

    def download_model(self, model_card: dict):
        """Download model files given an object specifying the file locations.
        Model card is in the format
        {
            "name": "name of this model",
            "language": "language targeted by this model",
            "version": "version of this model",
            "creator": "creator of this model",
            "acoustic": "URL to acoustic model",
            "scorer": "URL to scorer, optional"
        }

        Args:
            model_card (dict): model card as documented above.
        """
        card = ModelCard.new_from_dict(model_card)
        card.check_values()

        # Model files are put in a folder matching model name, inside install dir
        model_base_path = self.install_dir / card.name

        # Parse URL and derive file name to download acoustic model to
        acoustic_basename = Path(urllib.parse.urlparse(card.acoustic).path).name
        output_acoustic = model_base_path / acoustic_basename

        scorer_basename = None
        output_scorer = None
        if card.scorer:
            scorer_basename = Path(urllib.parse.urlparse(card.scorer).path).name
            output_scorer = model_base_path / scorer_basename

        install_id = uuid.uuid4()
        install_task = ModelInstallTask(
            model_manager=self,
            model_card=card,
            acoustic_url=card.acoustic,
            acoustic_path=output_acoustic,
            scorer_url=card.scorer,
            scorer_path=output_scorer,
        )
        self.set_install_task_state(install_id, install_task)
        install_task.start()
        return install_id

    def report_install_complete(
        self, model_card: ModelCard, acoustic_path: Path, scorer_path: Optional[Path]
    ):
        model_card.acoustic_path = acoustic_path
        model_card.scorer_path = scorer_path
        model_card.installed = True
        self.installed_models.models.append(model_card)
        self.persist_index_to_disk()
