# Coqui STT local server

This is a local server for trying out Coqui STT models.

# Usage

```bash
$ pip install coqui_stt_server
$ stt-server
```

# Build from source

```bash
$ # Create and activate virtualenv
$ python -m venv /tmp/venv
$ /tmp/venv/bin/activate
$ make dev_install
$ make install_pre_commit_hooks # Install pre-commit hooks for development
```

# Build Python package (sdist/wheel)

```bash
$ make package
$ ll dist/
```
