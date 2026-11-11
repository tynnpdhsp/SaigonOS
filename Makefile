# SPDX-License-Identifier: Apache-2.0
.PHONY: check lint format test lock third-party clean

UV_COMPILE = uv pip compile --quiet pyproject.toml --python-version 3.11 --custom-compile-command "make lock"
SPDX_TAG = SPDX-License-Identifier

check: lint test

lint:
	reuse lint
	ruff check .
	ruff format --check .
	python scripts/third_party.py --check

format:
	ruff check --fix .
	ruff format .

test:
	pytest --cov

lock:
	$(UV_COMPILE) -o requirements.txt
	$(UV_COMPILE) --group dev -c requirements.txt -o requirements-dev.txt
	sed -i '1i # $(SPDX_TAG): Apache-2.0' requirements.txt requirements-dev.txt

third-party:
	python scripts/third_party.py

clean:
	rm -rf build dist htmlcov .coverage coverage.xml .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
