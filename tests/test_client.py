"""Unit tests for the Trackman client and config — no network required."""

from __future__ import annotations

import httpx
import pytest

from trackman_mcp.client import (
    TrackmanAuthError,
    TrackmanClient,
    TrackmanGraphQLError,
)
from trackman_mcp.config import Config


def _config(token: str | None = "test-token") -> Config:
    return Config(token=token)


def test_config_strips_bearer_prefix(monkeypatch):
    monkeypatch.setenv("TRACKMAN_TOKEN", "Bearer abc.def.ghi")
    cfg = Config.from_env()
    assert cfg.token == "abc.def.ghi"
    assert cfg.has_token


def test_config_no_token(monkeypatch):
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)
    cfg = Config.from_env()
    assert cfg.token is None
    assert not cfg.has_token


async def test_execute_returns_data():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"data": {"me": {"profile": {"fullName": "Pat"}}}})

    transport = httpx.MockTransport(handler)
    async with TrackmanClient(_config(), transport=transport) as client:
        data = await client.execute("query { me { profile { fullName } } }")
    assert data["me"]["profile"]["fullName"] == "Pat"


async def test_execute_raises_on_401():
    transport = httpx.MockTransport(lambda r: httpx.Response(401, text="nope"))
    async with TrackmanClient(_config(), transport=transport) as client:
        with pytest.raises(TrackmanAuthError):
            await client.execute("query { me { profile { fullName } } }")


async def test_execute_raises_on_graphql_errors():
    body = {"errors": [{"message": "boom"}], "data": None}
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    async with TrackmanClient(_config(), transport=transport) as client:
        with pytest.raises(TrackmanGraphQLError):
            await client.execute("query { me { profile { fullName } } }")


async def test_execute_requires_token():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {}}))
    async with TrackmanClient(_config(token=None), transport=transport) as client:
        with pytest.raises(TrackmanAuthError):
            await client.execute("query { __typename }")
