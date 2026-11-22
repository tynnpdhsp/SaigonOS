# SPDX-License-Identifier: Apache-2.0
.PHONY: check lint format test integration lock dependencies schema dist clean

VERSION ?= $(shell python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
UV_COMPILE = uv pip compile --quiet --custom-compile-command "make lock"
CORE_LOCK = src/saigonos/stack/core/requirements.txt
APP_SCHEMA = schemas/saigonos-app.schema.json
SPDX_TAG = SPDX-License-Identifier

check: lint test

lint:
	reuse lint
	ruff check .
	ruff format --check .
	python scripts/dependencies.py --check

format:
	ruff check --fix .
	ruff format .

test:
	pytest --cov

integration:
	pytest -m integration -v

lock:
	$(UV_COMPILE) pyproject.toml --python-version 3.11 -o requirements.txt
	$(UV_COMPILE) --group core --python-version 3.14 --generate-hashes -o $(CORE_LOCK)
	$(UV_COMPILE) pyproject.toml --python-version 3.11 --group dev --group core -c requirements.txt -c $(CORE_LOCK) -o requirements-dev.txt
	sed -i '1i # $(SPDX_TAG): Apache-2.0' requirements.txt $(CORE_LOCK) requirements-dev.txt

dependencies:
	python scripts/dependencies.py

schema:
	PYTHONPATH=src/saigonos/stack/core python -m saigonos_core.apps schema > $(APP_SCHEMA)

dist:
	rm -rf dist
	mkdir dist
	git archive --format=tar.gz --prefix=saigonos-$(VERSION)/ -o dist/saigonos-$(VERSION).tar.gz HEAD
	cd dist && sha256sum saigonos-$(VERSION).tar.gz > SHA256SUMS

clean:
	rm -rf build dist htmlcov .coverage coverage.xml .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
