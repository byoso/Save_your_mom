.PHONY: help test test-verbose check

PYTHON := ./.venv/bin/python
PYTEST := $(PYTHON) -m pytest

help:
	@echo "Targets:"
	@echo "  make test         Run pytest quietly"
	@echo "  make test-verbose Run pytest with verbose output"
	@echo "  make check        Run the default test suite"

test:
	$(PYTEST) -q

test-verbose:
	$(PYTEST) -s -vv

check: test
