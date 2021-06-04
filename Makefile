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

dev_install: node_deps
	yarn build
	python -m pip install -e .

install_pre_commit_hooks: .pre-commit-config.yaml
	python .pre-commit-2.13.0.pyz install
