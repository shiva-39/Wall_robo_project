import os
import asyncio
import pytest
from fastapi import FastAPI
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi import Request

# Integration test that verifies slowapi Limiter works against a real Redis
# service. This test is skipped when REDIS_URL is not provided.

REDIS_URL = os.environ.get("REDIS_URL")

pytestmark = pytest.mark.asyncio


@pytest.mark.integration
@pytest.mark.skipif(not REDIS_URL, reason="Redis URL not provided")
async def test_redis_backed_limiter_works(event_loop):
    app = FastAPI()

    limiter = Limiter(key_func=get_remote_address, storage_uri=REDIS_URL)
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/limited")
    @limiter.limit("2/minute")
    async def limited(req: Request):
        return {"ok": True}

    # Use httpx AsyncClient against the app
    import httpx

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        r1 = await client.get("/limited")
        assert r1.status_code == 200
        r2 = await client.get("/limited")
        assert r2.status_code == 200
        r3 = await client.get("/limited")
        # Expect rate limited
        assert r3.status_code == 429

