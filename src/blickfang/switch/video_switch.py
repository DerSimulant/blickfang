"""Video-basierter Schalter (/LF510/) — Person A.

Nutzt den Schmitt-Trigger-Detektor als Signalquelle.
"""

from __future__ import annotations

from typing import Optional

from blickfang.calibration.profile import CalibrationProfile
from blickfang.core.events import ChannelFrame, SwitchEvent
from blickfang.detection.detector import SchmittTriggerDetector
from blickfang.switch.base import SwitchSource


class VideoSwitch(SwitchSource):
    """Detektor-gestützter virtueller Schalter.

    Wandelt erkannte Signale aus dem Schmitt-Trigger-Detektor
    in SwitchEvents um.
    """

    def __init__(self, profile: CalibrationProfile):
        super().__init__(source_id="video_switch")
        self._detector = SchmittTriggerDetector(profile)
        self._profile = profile

    @property
    def detector(self) -> SchmittTriggerDetector:
        """Zugriff auf den Detektor (für Monitor-Anzeige)."""
        return self._detector

    def process_frame(self, frame: ChannelFrame) -> Optional[SwitchEvent]:
        """Verarbeitet einen ChannelFrame.

        Args:
            frame: Aktueller ChannelFrame mit Kanalwerten.

        Returns:
            SwitchEvent wenn ein Signal emittiert wird.
        """
        if not self.enabled:
            return None

        event = self._detector.process(frame)
        if event is not None:
            self.emit(event)
        return event

    def start(self) -> None:
        """Startet den Video-Schalter."""
        self._detector.reset()

    def stop(self) -> None:
        """Stoppt den Video-Schalter."""
        pass
