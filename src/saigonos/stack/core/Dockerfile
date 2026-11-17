# SPDX-License-Identifier: Apache-2.0
FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app
COPY requirements.txt .
RUN pip install --require-hashes --only-binary :all: --requirement requirements.txt
COPY saigonos_core saigonos_core

USER nobody
EXPOSE 8000
CMD ["uvicorn", "saigonos_core.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
