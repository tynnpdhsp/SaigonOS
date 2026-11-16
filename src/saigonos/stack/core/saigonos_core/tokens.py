# SPDX-License-Identifier: Apache-2.0
import logging
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
)
REQUIRED_CLAIMS = ["exp", "iss", "sub"]
KEYS_LIFESPAN = 60
KEYS_COOLDOWN = 1
KEYS_TIMEOUT = 5

logger = logging.getLogger(__name__)


class InvalidTokenError(Exception):
    pass


class KeysUnavailableError(Exception):
    pass


class TokenVerifier:
    def __init__(
        self,
        issuer: str,
        jwks_url: str,
        lifespan: float = KEYS_LIFESPAN,
        cooldown: float = KEYS_COOLDOWN,
    ) -> None:
        self.issuer = issuer
        self.keys = PyJWKClient(
            jwks_url, lifespan=lifespan, cooldown_duration=cooldown, timeout=KEYS_TIMEOUT
        )

    def verify(self, token: str) -> dict[str, Any]:
        try:
            key = self.keys.get_signing_key_from_jwt(token)
            if key.algorithm_name not in ALGORITHMS:
                raise InvalidTokenError
            return jwt.decode(
                token,
                key,
                algorithms=[key.algorithm_name],
                issuer=self.issuer,
                options={"require": REQUIRED_CLAIMS, "verify_aud": False},
            )
        except PyJWKClientConnectionError as error:
            logger.warning("Không lấy được JWKS của Keycloak: %s", error)
            raise KeysUnavailableError from error
        except PyJWTError as error:
            raise InvalidTokenError from error
