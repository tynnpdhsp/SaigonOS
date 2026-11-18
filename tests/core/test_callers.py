# SPDX-License-Identifier: Apache-2.0
import pytest

from saigonos_core.callers import caller_of


def test_call_without_token_is_anonymous():
    caller = caller_of(None)

    assert (caller.role, caller.authenticated) == ("anon", False)
    assert caller.claims == {"role": "anon"}


def test_token_with_realm_role_authenticated_is_user(realm):
    claims = realm.claims()

    caller = caller_of(claims)

    assert (caller.role, caller.authenticated) == ("authenticated", True)
    assert caller.claims == claims | {"role": "authenticated"}
    assert "role" not in claims


@pytest.mark.parametrize(
    "access",
    [
        None,
        {},
        {"roles": []},
        {"roles": ["offline_access"]},
        {"roles": "authenticated"},
        {"roles": None},
        "authenticated",
        ["authenticated"],
    ],
)
def test_token_without_realm_role_authenticated_is_anonymous_with_its_claims(realm, access):
    claims = realm.claims(realm_access=access)

    caller = caller_of(claims)

    assert (caller.role, caller.authenticated) == ("anon", False)
    assert caller.claims == claims | {"role": "anon"}
    assert caller.claims["sub"] == realm.subject


def test_realm_roles_come_from_token(realm):
    caller = caller_of(realm.claims(realm_access={"roles": ["authenticated", "nhan-vien", 7]}))

    assert caller.realm_roles == {"authenticated", "nhan-vien"}


@pytest.mark.parametrize("access", [None, {}, {"roles": "nhan-vien"}, ["nhan-vien"]])
def test_token_without_list_of_realm_roles_has_none(realm, access):
    assert caller_of(realm.claims(realm_access=access)).realm_roles == frozenset()


def test_role_claim_sent_in_token_is_replaced(realm):
    caller = caller_of(realm.claims(role="postgres", realm_access={"roles": []}))

    assert caller.role == "anon"
    assert caller.claims["role"] == "anon"
