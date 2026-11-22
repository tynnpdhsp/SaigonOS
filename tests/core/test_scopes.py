# SPDX-License-Identifier: Apache-2.0
import asyncio
from contextlib import asynccontextmanager

import pytest

from saigonos_core.callers import caller_of
from saigonos_core.scopes import FIND, Scope, Scopes


class FakeConnection:
    def __init__(self, apps, asked):
        self.apps = apps
        self.asked = asked

    async def fetchval(self, query, name):
        self.asked.append((query, name))
        return name in self.apps


class FakeDatabase:
    def __init__(self, *apps):
        self.apps = set(apps)
        self.asked = []

    @asynccontextmanager
    async def transaction(self):
        yield FakeConnection(self.apps, self.asked)


def scope_of(database, claims):
    return asyncio.run(Scopes(database).of(caller_of(claims)))


def test_token_of_installed_app_gets_scope_of_app():
    database = FakeDatabase("nghi-phep")

    found = scope_of(database, {"sub": "a", "azp": "nghi-phep"})

    assert found == Scope("nghi-phep")
    assert found.query == {"tenantIdIn": ["nghi-phep"]}
    assert database.asked == [(FIND, "nghi-phep")]


@pytest.mark.parametrize(
    "claims",
    [{"sub": "a", "azp": "kiem-thu"}, {"sub": "a"}, {"sub": "a", "azp": ""}, {"azp": 7}],
    ids=["client-khac", "khong-co-azp", "azp-rong", "azp-khong-phai-chuoi"],
)
def test_other_tokens_get_processes_outside_apps(claims):
    found = scope_of(FakeDatabase("nghi-phep"), claims)

    assert found == Scope()
    assert found.query == {"withoutTenantId": True}


def test_scope_holds_only_items_of_its_tenant():
    item, other = {"tenantId": "nghi-phep"}, {"tenantId": None}

    assert (Scope("nghi-phep").holds(item), Scope("nghi-phep").holds(other)) == (True, False)
    assert (Scope().holds(item), Scope().holds(other), Scope().holds({})) == (False, True, True)
