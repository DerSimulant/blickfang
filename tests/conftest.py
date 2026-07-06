"""Gemeinsame Test-Fixtures für blickfang."""

import pytest
import numpy as np

from blickfang.calibration.profile import CalibrationProfile
from blickfang.core.config import AppConfig, load_config
from blickfang.core.events import ChannelFrame, QualityState


@pytest.fixture
def sample_profile():
    """Ein Standard-Testprofil."""
    return CalibrationProfile(
        person_name="test_person",
        channel_name="ear_left",
        channel_direction=1,
        baseline_median=0.3,
        baseline_mad=0.05,
        mad_floor=0.01,
        threshold_delta=0.15,
        hold_time_s=0.3,
        refractory_s=0.5,
        confirmation_pattern="single",
    )


@pytest.fixture
def sample_config():
    """Eine Standard-Testkonfiguration."""
    return AppConfig()


@pytest.fixture
def resting_frames():
    """100 Frames mit Ruhewerten."""
    rng = np.random.default_rng(42)
    frames = []
    for i in range(100):
        frame = ChannelFrame(
            timestamp=i * 0.033,
            channels={
                "ear_left": 0.3 + rng.normal(0, 0.02),
                "ear_right": 0.3 + rng.normal(0, 0.02),
                "brow_left": 0.15 + rng.normal(0, 0.01),
            },
            quality=QualityState.OK,
            raw_fps=30.0,
        )
        frames.append(frame)
    return frames
