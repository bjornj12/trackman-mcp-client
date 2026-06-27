"""Configuration loaded from environment variables.

Secrets come from the environment only — never hardcode or log them.
See .env.example for the full list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

GRAPHQL_ENDPOINT = "https://api.trackmangolf.com/graphql"
OIDC_ISSUER = "https://login.trackmangolf.com"
USERINFO_ENDPOINT = f"{OIDC_ISSUER}/connect/userinfo"

# The public web-portal client id, observed from the portal's login redirect.
# Used only for reference / future OAuth work; the MCP does not run the exchange.
WEB_PORTAL_CLIENT_ID = "golf-portal.2dad6810-ef7c-4a0d-9c0a-0eaae2fb9e98"


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the Trackman MCP."""

    token: str | None
    graphql_endpoint: str = GRAPHQL_ENDPOINT
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Config":
        token = os.environ.get("TRACKMAN_TOKEN") or None
        if token:
            token = token.strip()
            # Tolerate users pasting the whole "Bearer xxx" header value.
            if token.lower().startswith("bearer "):
                token = token[7:].strip()
        endpoint = os.environ.get("TRACKMAN_GRAPHQL_ENDPOINT", GRAPHQL_ENDPOINT)
        timeout = float(os.environ.get("TRACKMAN_TIMEOUT_SECONDS", "30"))
        return cls(token=token, graphql_endpoint=endpoint, timeout_seconds=timeout)

    @property
    def has_token(self) -> bool:
        return bool(self.token)
