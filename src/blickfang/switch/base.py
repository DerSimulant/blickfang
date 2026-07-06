"""Switch-Schnittstelle (/LF500/, /LF510/).

Schalterquellen sind austauschbar: video_switch und key_switch
implementieren dieselbe Schnittstelle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from blickfang.core.events import SwitchEvent


class SwitchSource(ABC):
    """Abstrakte Basis für alle Schalterquellen.

    Referenz: /LF510/ — Austauschbare Quellen für den virtuellen Schalter.
    """

    def __init__(self, source_id: str):
        self._source_id = source_id
        self._callback: Optional[Callable[[SwitchEvent], None]] = None
        self._enabled = True

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def set_callback(self, callback: Callable[[SwitchEvent], None]) -> None:
        """Setzt den Callback für emittierte Events."""
        self._callback = callback

    def emit(self, event: SwitchEvent) -> None:
        """Emittiert ein SwitchEvent an den registrierten Callback."""
        if self._enabled and self._callback is not None:
            self._callback(event)

    @abstractmethod
    def start(self) -> None:
        """Startet die Schalterquelle."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stoppt die Schalterquelle."""
        ...
