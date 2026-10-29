"""RMS brand for exported reports (RMS Brand Guide, RMS BRD/GUI/01, first edition).

Colours (web values from the guide): corporate blue Pantone 285 C #0071CE is the
dominant colour; green Pantone 354 C #00AE42 is the secondary colour; yellow
Pantone 7408 C #F7BE00 is an accent that never covers more than 20% of an area.
Each comes in 80 / 60 / 40 / 20% tones. Typefaces: Effra for headings and key
figures, Open Sans for body text (heading 40 pt, sub-header 20 pt, body 9 pt in
print). Logo: the full-colour logo on white or light backgrounds, the white
version on blue; never stretched, recoloured or given effects; clear space of
half the circle's width on every side. Tagline: "Delivering Supplies, Building
Trust.", below the logo and outside its clear space.

The logo files live in app/reporting/assets/brand/ (rms-logo.png and
rms-logo-white.png). When they are absent, reports are built without a logo:
the logo is never redrawn or imitated.

Red is not a brand colour; it is used only as a status colour (shortfall,
overdue), sparingly.
"""

from functools import cache
from importlib import resources

BLUE = "0071CE"
GREEN = "00AE42"
YELLOW = "F7BE00"
WHITE = "FFFFFF"
INK = "26323F"  # body text: a dark neutral that reads well next to the brand blue
MUTED = "5E6B78"
LINE = "D5DDE5"
PANEL = "F3F6F9"
RED = "C0392B"  # status only

HEADING_FONT = "Effra"
BODY_FONT = "Open Sans"
# Web pages fall back when a reader does not have the brand fonts installed.
CSS_HEADING_FONT = '"Effra", "Open Sans", "Segoe UI", Arial, sans-serif'
CSS_BODY_FONT = '"Open Sans", "Segoe UI", Arial, sans-serif'

TAGLINE = "Delivering Supplies, Building Trust."
ORGANISATION = "Rwanda Medical Supply"
SHORT = "RMS"


def tint(colour: str, share: float) -> str:
    """The colour at `share` strength on white (the guide's 80 / 60 / 40 / 20% tones)."""
    channels = [int(colour[i : i + 2], 16) for i in (0, 2, 4)]
    mixed = [round(255 - (255 - c) * share) for c in channels]
    return "".join(f"{c:02X}" for c in mixed)


# Series colours for charts, in order: brand colours first, then their tones.
SERIES = [BLUE, GREEN, YELLOW, tint(BLUE, 0.6), tint(GREEN, 0.6), MUTED, tint(BLUE, 0.4)]

# Tones of KPI cards and highlight boxes: (accent, light fill).
TONES: dict[str, tuple[str, str]] = {
    "blue": (BLUE, tint(BLUE, 0.1)),
    "green": (GREEN, tint(GREEN, 0.1)),
    "yellow": ("B78C00", tint(YELLOW, 0.15)),  # darker yellow for text on white
    "red": (RED, "FBEAE8"),
    "grey": (MUTED, PANEL),
}


def rgb(colour: str) -> tuple[int, int, int]:
    return int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16)


@cache
def logo(variant: str = "colour") -> bytes | None:
    """The RMS logo PNG ("colour" for light backgrounds, "white" for blue), if installed."""
    name = "rms-logo.png" if variant == "colour" else "rms-logo-white.png"
    path = resources.files("app.reporting").joinpath("assets", "brand", name)
    return path.read_bytes() if path.is_file() else None


@cache
def logo_size(variant: str = "colour") -> tuple[int, int] | None:
    """Width and height in pixels of a logo file (to keep its proportions)."""
    content = logo(variant)
    if content is None or len(content) < 24 or content[12:16] != b"IHDR":
        return None
    return int.from_bytes(content[16:20], "big"), int.from_bytes(content[20:24], "big")


def footer(report: str, period: str, draft: bool) -> str:
    parts = [SHORT, report, period, "Draft for SMT" if draft else ""]
    return " · ".join(p for p in parts if p)
