# Convenience wrapper around the cross-platform Python CLI (`python -m nexo_os`).
# `make` is optional — every target maps 1:1 to a CLI command that works on Windows
# without make: e.g. `python -m nexo_os seed`.

PY ?= python

.PHONY: install seed bootstrap-admin run orchestrate test eval lint bq-validate

install:
	$(PY) -m pip install -e ".[dev]"

seed:
	$(PY) -m nexo_os seed

bootstrap-admin:
	$(PY) -m nexo_os bootstrap-admin

run:
	$(PY) -m nexo_os run

orchestrate:
	$(PY) -m nexo_os orchestrate

test:
	$(PY) -m nexo_os test

eval:
	$(PY) -m nexo_os eval

lint:
	$(PY) -m nexo_os lint

bq-validate:
	$(PY) -m nexo_os bq-validate
