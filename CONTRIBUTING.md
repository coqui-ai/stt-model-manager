# Contribution guidelines

Welcome to the 🐸STT communuty! We are excited to see your interest, and appreciate your support!

This repository is governed by the Contributor Covenant Code of Conduct. For more details, see the [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)

## How to Make a Good Pull Request

Here's some guidelines on how to make a good PR to 🐸STT.

### Bug-fix PR

You've found a bug and you were able to squash it! Great job! Please write a short but clear commit message describing the bug, and how you fixed it. This makes review much easier. Also, please name your branch something related to the bug-fix.

### New Feature PR

You've made some core changes to 🐸STT, and you would like to share them back with the community -- great! First things first: if you're planning to add a feature (not just fix a bug or docs) let the 🐸STT team know ahead of time and get some feedback early. A quick check-in with the team can save time during code-review, and also ensure that your new feature fits into the project.

The 🐸STT codebase is made of many connected parts. There is Python code for training 🐸STT, core C++ code for running inference on trained models, and multiple language bindings to the C++ core so you can use 🐸STT in your favorite language.

Whenever you add a new feature to 🐸STT and what to contribute that feature back to the project, here are some things to keep in mind:

1. You've made changes to the Python code. Make sure you run a linter (described below).

## Requesting review on your PR

Generally, a code owner will be notified of your pull request and will either review it or ask some other code owner for their review. If you'd like to proactively request review as you open the PR, see the the CODE_OWNERS.rst file which describes who's an appropriate reviewer depending on which parts of the code you're changing.


## Code linting

We use [pre-commit](https://pre-commit.com/) to manage pre-commit hooks that take care of checking your changes for code style violations. Before committing changes, make sure you have the hook installed in your setup by running, in the virtual environment you use for running the code:

```bash
$ # Create and activate virtualenv:
$ python -m venv /tmp/venv
$ /tmp/venv/bin/activate
$ # Install package in editable mode:
$ make dev_install
$ # Install pre-commit hooks for development:
$ make install_pre_commit_hooks
```

This will install a git pre-commit hook which will check your commits and let you know about any style violations that need fixing.
