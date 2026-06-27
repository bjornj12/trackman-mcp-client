"""Browser-assisted login: capture a Trackman Bearer token via a real browser.

The user signs in once in an isolated browser profile (we never see the
password). We capture the access token the portal sends to the GraphQL API and
cache it. Because the profile persists the portal session, later runs can
refresh the token headlessly with no re-login.

Playwright is an optional dependency — install with: uv pip install -e '.[login]'
then `playwright install chromium` (or have Google Chrome installed).
"""

from __future__ import annotations

import asyncio

from . import token_store

PORTAL_URL = "https://portal.trackmangolf.com/"
GRAPHQL_HOST = "api.trackmangolf.com/graphql"


class TrackmanLoginError(Exception):
    """Login/capture failed (e.g. user didn't finish, or session expired)."""


async def capture_token(headless: bool = False, timeout_seconds: float = 300.0) -> str:
    """Open the portal, capture the Bearer token, cache it, and return it.

    Args:
        headless: run without a visible window. Use True only for silent refresh
            when the persisted session is still valid; the first login must be
            headed so the user can sign in.
        timeout_seconds: how long to wait for a token to appear.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise TrackmanLoginError(
            "Playwright is not installed. Run: uv pip install -e '.[login]' "
            "&& playwright install chromium"
        ) from exc

    captured: dict[str, str] = {}
    done = asyncio.Event()
    seen = {"requests": 0, "bearer_hosts": set()}

    def _take(token: str, source: str) -> None:
        if token and token.count(".") >= 2 and "token" not in captured:
            captured["token"] = token.strip()
            print(f"  ▸ captured token ({source}).")
            done.set()

    async def inspect_request(request: object) -> None:
        try:
            url = getattr(request, "url", "")
            if "trackman" not in url or "token" in captured:
                return
            seen["requests"] += 1
            headers = await request.all_headers()
            auth = headers.get("authorization") or headers.get("Authorization")
            if auth and auth.lower().startswith("bearer "):
                from urllib.parse import urlparse

                seen["bearer_hosts"].add(urlparse(url).netloc)
                _take(auth[7:], "network")
        except Exception:
            pass

    def on_request(request: object) -> None:
        asyncio.create_task(inspect_request(request))

    async def poll_storage(page: object) -> None:
        """Some SPAs keep the token in web storage (oidc-client). Poll for it."""
        script = """() => {
            const hits = [];
            for (const s of [window.localStorage, window.sessionStorage]) {
                for (let i = 0; i < s.length; i++) {
                    const v = s.getItem(s.key(i));
                    if (v && v.indexOf('access_token') !== -1) hits.push(v);
                }
            }
            return hits;
        }"""
        while not done.is_set():
            try:
                for raw in await page.evaluate(script):
                    import json as _json

                    try:
                        tok = _json.loads(raw).get("access_token")
                    except Exception:
                        tok = None
                    if tok:
                        _take(tok, "storage")
            except Exception:
                pass
            await asyncio.sleep(2)

    async with async_playwright() as p:
        launch_kwargs = {
            "user_data_dir": str(token_store.browser_profile_dir()),
            "headless": headless,
        }
        try:
            context = await p.chromium.launch_persistent_context(
                channel="chrome", **launch_kwargs
            )
        except Exception:
            context = await p.chromium.launch_persistent_context(**launch_kwargs)

        context.on("request", on_request)
        page = context.pages[0] if context.pages else await context.new_page()
        poller = None
        try:
            await page.goto(PORTAL_URL, wait_until="domcontentloaded")
            print("  ▸ portal open — sign in if prompted; waiting for token…")
            poller = asyncio.create_task(poll_storage(page))
            await asyncio.wait_for(done.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            hosts = ", ".join(sorted(seen["bearer_hosts"])) or "none"
            raise TrackmanLoginError(
                "No token captured before timeout. "
                f"(Trackman requests seen: {seen['requests']}; "
                f"bearer hosts: {hosts}.) If a window opened, finish signing in. "
                "If you were signed in but nothing was captured, the portal may "
                "proxy the token server-side — tell me and I'll adjust."
            ) from exc
        finally:
            if poller:
                poller.cancel()
            await context.close()

    token = captured.get("token")
    if not token:
        raise TrackmanLoginError("Login finished but no Bearer token was seen.")
    token_store.save_token(token)
    return token
