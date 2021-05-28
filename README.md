# Coqui STT local server

This is a local server for trying out Coqui STT models.

# Usage

```bash
$ pip install coqui_stt_server
$ stt-server
```

# Development install

```bash
$ # Create and activate virtualenv
$ pip install -e .
$ pip uninstall coqpit
$ cd coqpit; pip install .
$ python .pre-commit-2.13.0.pyz install # Install pre-commit hooks for development
```
