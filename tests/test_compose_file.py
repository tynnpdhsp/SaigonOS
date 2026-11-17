# SPDX-License-Identifier: Apache-2.0
import re
from importlib.resources import files

import pytest

COMPOSE = (files("saigonos") / "stack" / "compose.yaml").read_text(encoding="utf-8")


def services():
    section = COMPOSE.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    blocks = {}
    name = None
    for line in section.splitlines():
        header = re.fullmatch(r"  ([a-z]+):", line)
        if header:
            name = header[1]
            blocks[name] = []
        elif name:
            blocks[name].append(line.strip())
    return blocks


LONG_RUNNING = [name for name, lines in services().items() if "restart: unless-stopped" in lines]


def test_stack_lists_long_running_services():
    assert {"postgres", "keycloak", "seaweedfs", "clamav", "freshclam", "core"} <= set(LONG_RUNNING)


@pytest.mark.parametrize("name", LONG_RUNNING)
def test_long_running_service_has_healthcheck_that_compose_2_can_wait_for(name):
    lines = services()[name]
    checks = [line for line in lines if line.startswith("test:")]

    assert "healthcheck:" in lines
    assert len(checks) == 1
    assert "NONE" not in checks[0]
    assert "disable: true" not in lines
