"""
The Calendar entity.

A user can own multiple calendars (Personal, Work, Family, Fitness,
Holidays, etc.) — each with its own color and visibility toggle.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Calendar:
    """
    A named, colored calendar that contains events.

    Calendars can be shown/hidden independently — the UI respects the
    `visible` flag when rendering events.
    """
    id: str
    name: str
    color: str = "#D4AF37"          # gold by default
    visible: bool = True
    description: str = ""
    is_default: bool = False
    is_readonly: bool = False       # true for built-in holiday calendars
    owner: str = "me"

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"cal-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "visible": self.visible,
            "description": self.description,
            "is_default": self.is_default,
            "is_readonly": self.is_readonly,
            "owner": self.owner,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Calendar":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", "Untitled"),
            color=data.get("color", "#D4AF37"),
            visible=data.get("visible", True),
            description=data.get("description", ""),
            is_default=data.get("is_default", False),
            is_readonly=data.get("is_readonly", False),
            owner=data.get("owner", "me"),
        )

    @classmethod
    def create(cls, name: str, color: str = "#D4AF37",
               description: str = "") -> "Calendar":
        return cls(
            id=f"cal-{uuid.uuid4().hex[:8]}",
            name=name,
            color=color,
            description=description,
        )


# ---- Color palette for new calendars ----

CALENDAR_COLORS = [
    "#D4AF37",  # gold (default)
    "#5A7FA8",  # blue
    "#5A8A5A",  # green
    "#A85A8A",  # pink
    "#A87A4A",  # orange
    "#7A5AA8",  # purple
    "#5AA8A8",  # teal
    "#A85A5A",  # red
    "#8A8A4A",  # olive
    "#4A8AA8",  # sky
]
