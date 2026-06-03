"""Autonomy levels A0–A5 (spec §5.1). Ordered, so comparisons express authority."""

from enum import IntEnum


class AutonomyLevel(IntEnum):
    A0 = 0  # Advisory only
    A1 = 1  # Draft mode
    A2 = 2  # Controlled build
    A3 = 3  # Staging autonomy
    A4 = 4  # Production prepared (human approval to deploy)
    A5 = 5  # Conditional production autonomy
