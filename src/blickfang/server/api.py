"""FastAPI-Backend mit WebSocket-Bridge.

Verbindet den Erkennungs-Kern (Kamera, Detektor, Scanning-Engine)
mit dem React-Frontend über WebSocket.

Architektur:
  Python-Backend (localhost:8000)
    ├── /ws          → WebSocket: Events an Frontend senden
    ├── /api/status  → System-Status
    ├── /api/config  → Konfiguration lesen/schreiben
    ├── /api/profiles → Profile auflisten
    └── Kamera + Detektor laufen im Hintergrund

  React-Frontend (localhost:5173 dev / localhost:8000 prod)
    └── Empfängt Events, rendert Scanning-UI
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="blickfang", version="0.2.0")

# CORS für Entwicklung (Vite dev server auf :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Globaler Zustand
_connections: Set[WebSocket] = set()
_engine_state: Dict[str, Any] = {
    "mode": "idle",
    "phase": "idle",
    "current_row": 0,
    "current_col": -1,
    "selected_item": None,
    "text_buffer": "",
    "predictions": [],
    "confirm_progress": 0.0,
    "layout": None,
    "fatigue": {"level": "normal", "session_min": 0},
}


# ─── Pydantic-Modelle ──────────────────────────────────────────────────


class StatusResponse(BaseModel):
    running: bool = False
    mode: str = "idle"
    camera_active: bool = False
    person: str = ""
    scan_speed_s: float = 1.5
    uptime_s: float = 0.0


class ConfigUpdate(BaseModel):
    scan_speed_s: Optional[float] = None
    cancel_countdown_s: Optional[float] = None
    speak_on_highlight: Optional[bool] = None


class ProfileInfo(BaseModel):
    name: str
    channel: str = ""
    created: str = ""
    path: str = ""


# ─── WebSocket-Broadcast ───────────────────────────────────────────────


async def broadcast(event_type: str, data: Dict[str, Any]) -> None:
    """Sendet ein Event an alle verbundenen Clients."""
    message = json.dumps({"type": event_type, "data": data, "ts": time.time()})
    disconnected = set()
    for ws in _connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    _connections -= disconnected


def broadcast_sync(event_type: str, data: Dict[str, Any]) -> None:
    """Synchrone Version für Aufrufe aus dem Scanning-Thread."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast(event_type, data))
        else:
            loop.run_until_complete(broadcast(event_type, data))
    except RuntimeError:
        # Kein Event-Loop vorhanden — erstelle einen Task
        pass


# ─── REST-Endpoints ────────────────────────────────────────────────────


@app.get("/api/status")
async def get_status() -> StatusResponse:
    """Gibt den aktuellen System-Status zurück."""
    from blickfang.server.bridge import get_bridge
    bridge = get_bridge()
    if bridge:
        return StatusResponse(
            running=bridge.running,
            mode=bridge.mode,
            camera_active=bridge.camera_active,
            person=bridge.person,
            scan_speed_s=bridge.scan_speed_s,
            uptime_s=bridge.uptime_s,
        )
    return StatusResponse()


@app.get("/api/profiles")
async def list_profiles() -> List[ProfileInfo]:
    """Listet alle verfügbaren Profile."""
    profiles_dir = Path(__file__).resolve().parents[3] / "config" / "profiles"
    profiles = []
    if profiles_dir.exists():
        import yaml
        for path in sorted(profiles_dir.glob("*.yaml")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                profiles.append(ProfileInfo(
                    name=path.stem,
                    channel=data.get("channel", ""),
                    created=data.get("created", ""),
                    path=str(path),
                ))
            except Exception:
                profiles.append(ProfileInfo(name=path.stem, path=str(path)))
    return profiles


@app.get("/api/layouts")
async def list_layouts():
    """Listet alle verfügbaren Scanning-Layouts."""
    from blickfang.scanning.layouts import list_layouts
    return list_layouts()


@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    """Aktualisiert die Laufzeit-Konfiguration."""
    from blickfang.server.bridge import get_bridge
    bridge = get_bridge()
    if bridge:
        bridge.update_config(config.dict(exclude_none=True))
    return {"status": "ok"}


@app.post("/api/signal")
async def send_signal():
    """Sendet ein manuelles Signal (z.B. von einem Button im UI)."""
    from blickfang.server.bridge import get_bridge
    bridge = get_bridge()
    if bridge:
        bridge.signal()
    return {"status": "ok"}


@app.post("/api/mode/{mode}")
async def switch_mode(mode: str):
    """Wechselt den Kommunikations-Modus."""
    from blickfang.server.bridge import get_bridge
    bridge = get_bridge()
    if bridge:
        bridge.switch_mode(mode)
    return {"status": "ok", "mode": mode}


@app.post("/api/start")
async def start_communication(person: str = "", key_only: bool = True):
    """Startet die Kommunikation."""
    from blickfang.server.bridge import get_bridge
    bridge = get_bridge()
    if bridge:
        bridge.start(person=person, key_only=key_only)
    return {"status": "ok"}


@app.post("/api/stop")
async def stop_communication():
    """Stoppt die Kommunikation."""
    from blickfang.server.bridge import get_bridge
    bridge = get_bridge()
    if bridge:
        bridge.stop()
    return {"status": "ok"}


# ─── WebSocket-Endpoint ────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket-Verbindung für Echtzeit-Events."""
    await ws.accept()
    _connections.add(ws)
    logger.info(f"WebSocket verbunden ({len(_connections)} aktiv)")

    try:
        # Initialen Zustand senden
        await ws.send_text(json.dumps({
            "type": "state",
            "data": _engine_state,
            "ts": time.time(),
        }))

        # Auf Nachrichten vom Client warten
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "signal":
                # Client sendet Signal (Tastendruck im Browser)
                from blickfang.server.bridge import get_bridge
                bridge = get_bridge()
                if bridge:
                    bridge.signal()

            elif msg.get("type") == "mode":
                from blickfang.server.bridge import get_bridge
                bridge = get_bridge()
                if bridge:
                    bridge.switch_mode(msg.get("data", "main_menu"))

            elif msg.get("type") == "config":
                from blickfang.server.bridge import get_bridge
                bridge = get_bridge()
                if bridge:
                    bridge.update_config(msg.get("data", {}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket-Fehler: {e}")
    finally:
        _connections.discard(ws)
        logger.info(f"WebSocket getrennt ({len(_connections)} aktiv)")


# ─── Static Files (Produktions-Build) ──────────────────────────────────

_frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React SPA für alle nicht-API-Routen."""
        file_path = _frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dist / "index.html"))
