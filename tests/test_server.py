"""Full-flow tests for every MCP tool against mocked API responses.

Each test feeds a realistic GraphQL `data` payload through a MockTransport and
asserts the tool returns the right stats substructure. This proves the
extraction logic for all 9 tools without needing a live token; the only thing
left for real validation is live data.
"""

from __future__ import annotations

import httpx
import pytest

from trackman_mcp import server
from trackman_mcp.client import TrackmanClient
from trackman_mcp.config import Config


@pytest.fixture
def patch_transport(monkeypatch):
    """Patch server._run to use a MockTransport returning a canned payload."""

    def _install(payload: dict):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": payload})

        transport = httpx.MockTransport(handler)

        async def fake_run(query, variables=None):
            cfg = Config(token="test-token")
            async with TrackmanClient(cfg, transport=transport) as client:
                return await client.execute(query, variables)

        monkeypatch.setattr(server, "_run", fake_run)

    return _install


async def test_get_profile(patch_transport):
    patch_transport({"me": {
        "profile": {"fullName": "Pat Golfer", "outdoorHandicap": 8.4},
        "hcp": {"currentHcp": 8.2, "currentRecord": {"hcpNew": 8.2}},
    }})
    result = await server.get_profile()
    assert result["profile"]["fullName"] == "Pat Golfer"
    assert result["hcp"]["currentHcp"] == 8.2


async def test_get_handicap(patch_transport):
    patch_transport({"me": {"hcp": {
        "currentHcp": 8.2,
        "playerHistory": {"totalCount": 1, "items": [{"hcpNew": 8.2, "scoreDifferential": 7.1}]},
    }}})
    result = await server.get_handicap(take=5)
    assert result["playerHistory"]["totalCount"] == 1


async def test_list_sessions(patch_transport):
    patch_transport({"me": {"activities": {
        "totalCount": 2,
        "items": [
            {"id": "a1", "kind": "RANGE_PRACTICE", "numberOfStrokes": 40},
            {"id": "a2", "kind": "COURSE_PLAY", "grossScore": 82},
        ],
    }}})
    result = await server.list_sessions(take=25)
    assert result["totalCount"] == 2
    assert len(result["items"]) == 2


async def test_get_session(patch_transport):
    patch_transport({"node": {
        "__typename": "RangePracticeActivity",
        "id": "a1",
        "strokes": [{"club": "IRON7", "measurement": {"ballSpeed": 110.0, "carry": 165.0}}],
    }})
    result = await server.get_session(activity_id="a1")
    assert result["__typename"] == "RangePracticeActivity"
    assert result["strokes"][0]["measurement"]["carry"] == 165.0


async def test_get_course_rounds(patch_transport):
    patch_transport({"me": {"scorecards": [
        {"id": "s1", "grossScore": 82, "toPar": 10,
         "stat": {"greenInRegulation": 7, "numberOfPutts": 31}},
    ]}})
    result = await server.get_course_rounds(take=20)
    assert result["scorecards"][0]["stat"]["numberOfPutts"] == 31


async def test_get_club_stats(patch_transport):
    patch_transport({"me": {"equipment": {"clubs": [
        {"displayName": "7 Iron",
         "findMyDistance": {"numberOfShots": 30,
                            "clubStats": {"carry": 165.0, "standardDeviationCarry": 4.2}}},
    ]}}})
    result = await server.get_club_stats()
    assert result["clubs"][0]["findMyDistance"]["clubStats"]["carry"] == 165.0


async def test_get_shot_data(patch_transport):
    patch_transport({"node": {
        "__typename": "CoursePlayActivity",
        "scorecard": {"holes": [{"shots": [
            {"club": "DRIVER", "measurement": {"ballSpeed": 165.0, "smashFactor": 1.48}},
        ]}]},
    }})
    result = await server.get_shot_data(activity_id="a2")
    shot = result["scorecard"]["holes"][0]["shots"][0]
    assert shot["measurement"]["smashFactor"] == 1.48


async def test_get_activity_summary(patch_transport):
    patch_transport({"me": {"activitySummary": {
        "totalCount": 2,
        "items": [{"kind": "RANGE_PRACTICE", "activityCount": 12}],
    }}})
    result = await server.get_activity_summary()
    assert result["items"][0]["activityCount"] == 12


async def test_authenticate_without_token(monkeypatch):
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)
    result = await server.authenticate()
    assert result["authenticated"] is False
