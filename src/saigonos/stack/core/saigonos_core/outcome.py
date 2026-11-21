# SPDX-License-Identifier: Apache-2.0
from typing import NamedTuple

SENT = "sent"
RETRY = "retry"
WAIT = "wait"
FAILED = "failed"
UNKNOWN = "unknown"


class Outcome(NamedTuple):
    result: str
    detail: str
    wait: int = 0


def describe(error: Exception) -> str:
    return str(error) or type(error).__name__
