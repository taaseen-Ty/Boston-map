"""Readers that turn raw exports into a flat list of location points.

Every point is a dict: {"lat", "lon", "time" (ISO 8601 or None), "source", "ref"}.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from PIL import Image

try:  # iPhone photos are HEIC; this plug-in lets Pillow open them.
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

PHOTO_EXTS = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".tif", ".tiff", ".dng"}

GPS_IFD = 0x8825
EXIF_IFD = 0x8769
DATETIME_ORIGINAL = 0x9003
DATETIME = 0x0132


# --------------------------------------------------------------------------- photos
def _to_degrees(dms, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W", b"S", b"W") else deg


def read_photo(path: Path) -> dict | None:
    """Return a point from a photo's EXIF GPS, or None if it has no location."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
    except Exception:
        return None
    gps = exif.get_ifd(GPS_IFD)
    if not gps or 2 not in gps or 4 not in gps:
        return None
    lat = _to_degrees(gps[2], gps.get(1))
    lon = _to_degrees(gps[4], gps.get(3))
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None

    raw = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) or exif.get(DATETIME)
    when = None
    if raw:
        try:
            when = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").isoformat()
        except ValueError:
            pass
    return {"lat": lat, "lon": lon, "time": when, "source": "photo", "ref": path.name}


def read_photos(folder: Path) -> list[dict]:
    points, skipped = [], 0
    for p in sorted(folder.rglob("*")):
        if p.suffix.lower() not in PHOTO_EXTS:
            continue
        pt = read_photo(p)
        if pt:
            points.append(pt)
        else:
            skipped += 1
    print(f"  photos: {len(points)} with location, {skipped} without")
    return points


# --------------------------------------------------------------------------- timeline
_NUM = r"(-?\d+(?:\.\d+)?)"
_LATLNG = re.compile(_NUM + r"\s*°?\s*,\s*" + _NUM)


def _parse_latlng(value) -> tuple[float, float] | None:
    """Handle '42.36°, -71.05°', 'geo:42.36,-71.05', or {latitudeE7, longitudeE7}."""
    if isinstance(value, dict):
        if "latitudeE7" in value:
            return value["latitudeE7"] / 1e7, value["longitudeE7"] / 1e7
        for k in ("latLng", "point", "placeLocation", "location"):
            if k in value:
                return _parse_latlng(value[k])
        return None
    if isinstance(value, str):
        m = _LATLNG.search(value)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None


def _iso(value) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None).isoformat() if dt.tzinfo is None else dt.isoformat()
    except ValueError:
        return None


def _segments(data):
    """Yield timeline segments from the iOS export, Android export, or old Takeout."""
    if isinstance(data, list):
        yield from data
    elif isinstance(data, dict):
        for key in ("semanticSegments", "timelineObjects", "locations"):
            if key in data:
                yield from data[key]


def read_timeline_file(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    points = []
    for seg in _segments(data):
        if not isinstance(seg, dict):
            continue
        start = _iso(seg.get("startTime"))

        # A "visit" = time spent at a place. These are what we map.
        visit = seg.get("visit") or seg.get("placeVisit")
        if visit:
            cand = visit.get("topCandidate") or visit.get("location") or visit
            ll = _parse_latlng(cand)
            if ll:
                # Only real place names; semanticType ("HOME", "Searched Address") is not a name.
                points.append({"lat": ll[0], "lon": ll[1], "time": start,
                               "source": "timeline", "ref": cand.get("name")})
            continue

        # Old Takeout "Records.json" raw points.
        if "latitudeE7" in seg:
            ll = _parse_latlng(seg)
            points.append({"lat": ll[0], "lon": ll[1], "time": _iso(seg.get("timestamp")),
                           "source": "timeline", "ref": None})

    print(f"  timeline {path.name}: {len(points)} visits")
    return points


def read_timelines(folder: Path) -> list[dict]:
    points = []
    for p in sorted(folder.glob("*.json")):
        try:
            points += read_timeline_file(p)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  ! could not read {p.name}: {e}")
    return points
