"""Server-Einstiegspunkt: Startet FastAPI + Bridge.

Startet den lokalen Server auf localhost:8000.
Das React-Frontend verbindet sich per WebSocket.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import webbrowser
import threading
import time

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="blickfang — Server starten",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Startet den lokalen blickfang-Server.
Das Frontend öffnet sich automatisch im Browser.

Beispiele:
  blickfang-server                    # Nur Tastatur
  blickfang-server --person Anna      # Mit Kamera-Profil
  blickfang-server --speed 2.0        # Langsameres Scanning
""",
    )
    parser.add_argument(
        "--person", "-p",
        help="Name der Person (lädt Profil für Kamera-Erkennung)",
    )
    parser.add_argument(
        "--key-only",
        action="store_true",
        default=True,
        help="Nur Tastatur-Steuerung (Standard)",
    )
    parser.add_argument(
        "--camera",
        action="store_true",
        help="Kamera-Erkennung aktivieren (braucht --person)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.5,
        help="Scan-Geschwindigkeit in Sekunden (Standard: 1.5)",
    )
    parser.add_argument(
        "--cancel-time",
        type=float,
        default=2.5,
        help="Cancel-Countdown in Sekunden (Standard: 2.5)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server-Port (Standard: 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Browser nicht automatisch öffnen",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Sprachausgabe deaktivieren",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Bridge erstellen
    from blickfang.server.bridge import create_bridge
    bridge = create_bridge(
        scan_speed_s=args.speed,
        cancel_countdown_s=args.cancel_time,
        tts_enabled=not args.no_tts,
    )

    # Kommunikation starten
    key_only = not args.camera
    bridge.start(person=args.person or "", key_only=key_only)

    print("\n" + "=" * 60)
    print("  blickfang — Server")
    print("=" * 60)
    print(f"  URL:     http://localhost:{args.port}")
    print(f"  Person:  {args.person or '(keine)'}")
    print(f"  Modus:   {'Tastatur' if key_only else 'Kamera + Tastatur'}")
    print(f"  Speed:   {args.speed}s pro Schritt")
    print(f"  Cancel:  {args.cancel_time}s Countdown")
    print(f"  TTS:     {'Aus' if args.no_tts else 'An'}")
    print("=" * 60)
    print("  Strg+C = Beenden")
    print("=" * 60 + "\n")

    # Browser öffnen (verzögert)
    if not args.no_browser:
        def _open_browser():
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{args.port}")
        threading.Thread(target=_open_browser, daemon=True).start()

    # Server starten
    import uvicorn

    class _Server(uvicorn.Server):
        def install_signal_handlers(self):
            pass  # Wir handhaben Signals selbst

    config = uvicorn.Config(
        "blickfang.server.api:app",
        host="0.0.0.0",
        port=args.port,
        log_level=args.log_level.lower(),
        reload=False,
    )

    server = _Server(config)

    # Event-Loop der Bridge setzen
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bridge.set_loop(loop)

    try:
        loop.run_until_complete(server.serve())
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()
        print("\n[Server beendet]")


if __name__ == "__main__":
    main()
