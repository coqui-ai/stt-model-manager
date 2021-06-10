.DEFAULT_GOAL := help
.PHONY: help package node_deps

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

node_deps: package.json
	yarn install

react_build: node_deps
	yarn build

package: react_build # build Python package
	python -m pip install build
	python -m build

dev_install: react_build
	python -m pip install -e ".[test]"

install: react_build
	python -m pip install .

install_test: react_build
	python -m pip install ".[test]"

install_pre_commit_hooks: .pre-commit-config.yaml
	python .pre-commit-2.13.0.pyz install

frontend_tests:
	yarn run test:client

backend_tests:
	pytest
