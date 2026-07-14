import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.irsdk_client import DemoTelemetrySource, IRSDKTelemetrySource
from server.browser import open_overlay_window, open_settings_window
from server.engine import StrategyEngine
from server.settings_store import OverlaySettings, load_settings, save_settings

STATIC_DIR = Path(__file__).parent / "static"
WS_PUSH_INTERVAL_S = 0.5


class FuelLimitRequest(BaseModel):
    max_fuel_l: float | None = None
    fuel_pct_available: float | None = None


def create_app(demo: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        source = DemoTelemetrySource() if demo else IRSDKTelemetrySource()
        engine = StrategyEngine(source)
        engine.start()
        app.state.engine = engine
        app.state.settings = load_settings()
        engine.set_overlay_settings(app.state.settings.auto_fuel_enabled, app.state.settings.auto_fuel_source)

        try:
            yield
        finally:
            engine.stop()

    app = FastAPI(title="PitStrategy", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse("/overlay")

    @app.get("/overlay")
    async def overlay_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "overlay.html")

    @app.get("/settings")
    async def settings_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "settings.html")

    @app.websocket("/ws/live")
    async def ws_live(websocket: WebSocket) -> None:
        await websocket.accept()
        engine: StrategyEngine = websocket.app.state.engine
        try:
            while True:
                # Settings are pushed on every tick (not just fetched once by
                # the overlay page on load) so a change made in the settings
                # window while the overlay is already open takes effect live,
                # the same way every other overlay figure does.
                payload = engine.latest()
                payload["settings"] = websocket.app.state.settings.model_dump()
                await websocket.send_json(payload)
                await asyncio.sleep(WS_PUSH_INTERVAL_S)
        except WebSocketDisconnect:
            pass

    @app.get("/api/settings")
    async def api_get_settings() -> OverlaySettings:
        return app.state.settings

    @app.post("/api/settings")
    async def api_post_settings(payload: OverlaySettings) -> OverlaySettings:
        app.state.settings = payload
        save_settings(payload)
        app.state.engine.set_overlay_settings(payload.auto_fuel_enabled, payload.auto_fuel_source)
        return payload

    @app.post("/api/fuel-limit")
    async def api_fuel_limit(payload: FuelLimitRequest) -> dict:
        app.state.engine.set_fuel_limit(payload.max_fuel_l, payload.fuel_pct_available)
        return app.state.engine.fuel_limit_status()

    @app.post("/api/fuel-limit/clear")
    async def api_fuel_limit_clear() -> dict:
        app.state.engine.clear_fuel_limit()
        return app.state.engine.fuel_limit_status()

    @app.get("/api/qualifying-baseline")
    async def api_qualifying_baseline() -> dict:
        baseline = app.state.engine.qualifying_baseline()
        if baseline is None:
            return {"available": False}
        return {"available": True, **asdict(baseline)}

    @app.post("/api/open-overlay")
    async def api_open_overlay(request: Request) -> dict:
        # Built from the incoming request's own host/port rather than a
        # hardcoded default, so this still works if the server was started
        # with --host/--port overrides.
        overlay_url = str(request.base_url).rstrip("/") + "/overlay"
        browser = open_overlay_window(overlay_url)
        if browser is None:
            raise HTTPException(status_code=500, detail="Could not launch a browser window")
        return {"opened": True, "browser": browser, "url": overlay_url}

    @app.post("/api/open-settings")
    async def api_open_settings(request: Request) -> dict:
        settings_url = str(request.base_url).rstrip("/") + "/settings"
        browser = open_settings_window(settings_url)
        if browser is None:
            raise HTTPException(status_code=500, detail="Could not launch a browser window")
        return {"opened": True, "browser": browser, "url": settings_url}

    return app
