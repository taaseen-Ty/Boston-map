"""Build web/data.json from your photo and Google Maps Timeline exports.

    python scripts/build.py                 # family version (everything, home labelled)
    python scripts/build.py --mode public   # resume version (home zones removed, coords fuzzed)
    python scripts/build.py --sample        # demo data, no exports needed
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from neighborhoods import NEIGHBORHOODS
from sources import read_photos, read_timelines

ROOT = Path(__file__).resolve().parent.parent


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _in_ring(lat, lon, ring) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _polygons(geom):
    return geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]


_BASEMAP = None


def nearest_area(lat, lon) -> str:
    """Official Boston neighborhood containing the point; else the nearest named area."""
    global _BASEMAP
    if _BASEMAP is None:
        f = ROOT / "web" / "basemap.json"
        _BASEMAP = json.loads(f.read_text())["neighborhoods"] if f.exists() else []
    for n in _BASEMAP:
        for poly in _polygons(n["geometry"]):
            if _in_ring(lat, lon, poly[0]) and not any(_in_ring(lat, lon, h) for h in poly[1:]):
                return n["name"]
    return min(NEIGHBORHOODS, key=lambda n: haversine_m(lat, lon, n[1], n[2]))[0]


def in_bbox(p, b) -> bool:
    return b["south"] <= p["lat"] <= b["north"] and b["west"] <= p["lon"] <= b["east"]


# --------------------------------------------------------------------------- privacy
def apply_privacy(points, privacy, mode):
    zones = [z for z in privacy.get("hide_zones", []) if z.get("lat") or z.get("lon")]
    out = []
    for p in points:
        zone = next((z for z in zones
                     if haversine_m(p["lat"], p["lon"], z["lat"], z["lon"]) <= z["radius_m"]), None)
        if zone and mode == "public":
            continue  # drop entirely
        if zone:  # family: snap to the zone centre so it shows as one labelled pin
            p = {**p, "lat": zone["lat"], "lon": zone["lon"], "zone": zone["label"]}
        out.append(p)
    return out


# --------------------------------------------------------------------------- clustering
def cluster(points, radius_m):
    places = []
    for p in sorted(points, key=lambda p: p["time"] or ""):
        key = p.get("zone")
        match = None
        for c in places:
            if key and c.get("zone") == key:
                match = c
                break
            if not key and not c.get("zone") and \
                    haversine_m(p["lat"], p["lon"], c["lat"], c["lon"]) <= radius_m:
                match = c
                break
        if match is None:
            match = {"lat": p["lat"], "lon": p["lon"], "zone": key, "members": []}
            places.append(match)
        match["members"].append(p)
        n = len(match["members"])
        if not key:  # running centroid
            match["lat"] += (p["lat"] - match["lat"]) / n
            match["lon"] += (p["lon"] - match["lon"]) / n
    return places


def thumbnail(path: Path, size=560) -> str | None:
    """Small JPEG as a data URI. Re-encoding drops all EXIF, so no GPS leaks."""
    import base64, io
    from PIL import Image, ImageOps
    try:
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    except Exception:
        return None
    im.thumbnail((size, size))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def summarise(places, names_override, photos_dir=None):
    result = []
    for i, c in enumerate(places):
        m = c["members"]
        times = sorted(t for t in (p["time"] for p in m) if t)
        days = {t[:10] for t in times}
        named = Counter(p["ref"] for p in m if p["source"] == "timeline" and p["ref"])
        area = nearest_area(c["lat"], c["lon"])
        pid = f"p{i:03d}"
        name = names_override.get(pid) or c.get("zone") or \
            (named.most_common(1)[0][0] if named else area)
        result.append({
            "id": pid,
            "name": name,
            "area": area,
            "lat": round(c["lat"], 5),
            "lon": round(c["lon"], 5),
            "days": len(days) or 1,
            "photos": sum(p["source"] == "photo" for p in m),
            "visits": sum(p["source"] == "timeline" for p in m),
            "first": times[0] if times else None,
            "last": times[-1] if times else None,
            "dates": sorted(days),
            "pics": [t for t in (thumbnail(photos_dir / p["ref"]) for p in m
                                 if photos_dir and p["source"] == "photo") if t],
        })
    result.sort(key=lambda r: r["first"] or "9999")
    return result


# --------------------------------------------------------------------------- sample data
SAMPLE_SPOTS = [
    ("Logan Airport", 42.3656, -71.0096, 1),
    ("BU Questrom", 42.3497, -71.0995, 30),
    ("Mugar Library", 42.3511, -71.1081, 12),
    ("Boston Common", 42.3550, -71.0656, 4),
    ("Public Garden", 42.3540, -71.0703, 3),
    ("Newbury Street", 42.3499, -71.0842, 5),
    ("Fenway Park", 42.3467, -71.0972, 2),
    ("North End", 42.3640, -71.0545, 3),
    ("Seaport", 42.3510, -71.0440, 2),
    ("Harvard Square", 42.3736, -71.1190, 2),
    ("Kendall / MIT", 42.3625, -71.0860, 1),
    ("Charles River Esplanade", 42.3560, -71.0770, 6),
    ("Chinatown", 42.3505, -71.0620, 3),
    ("Coolidge Corner", 42.3420, -71.1213, 2),
    ("Castle Island", 42.3376, -71.0122, 1),
]


def sample_points(start: str):
    rng = random.Random(7)
    t0 = datetime.fromisoformat(start)
    pts = []
    for i, (name, lat, lon, n) in enumerate(SAMPLE_SPOTS):
        for _ in range(n):
            day = 0 if i == 0 else rng.randint(1, 66)
            t = t0 + timedelta(days=day, hours=rng.randint(9, 21), minutes=rng.randint(0, 59))
            src = "timeline" if rng.random() < 0.5 else "photo"
            pts.append({"lat": lat + rng.gauss(0, 0.0002), "lon": lon + rng.gauss(0, 0.0002),
                        "time": t.isoformat(), "source": src,
                        "ref": name if src == "timeline" else f"IMG_{rng.randint(1000, 9999)}.HEIC"})
    return pts


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--mode", choices=["family", "public"])
    ap.add_argument("--sample", action="store_true", help="use built-in demo data")
    ap.add_argument("--photos", action="store_true",
                    help="embed photo thumbnails (family version only)")
    ap.add_argument("--out", help="default: web/data.json (family) or web/data.public.json (public)")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    mode = args.mode or cfg["privacy"].get("mode", "family")

    print("Reading exports…")
    if args.sample:
        points = sample_points(cfg["start_date"])
        print(f"  sample: {len(points)} points")
    else:
        points = read_photos(ROOT / "data" / "photos") + read_timelines(ROOT / "data" / "timeline")

    before = len(points)
    points = [p for p in points if in_bbox(p, cfg["bbox"])]
    start = cfg.get("start_date")
    if start:
        points = [p for p in points if not p["time"] or p["time"][:10] >= start]
    print(f"  kept {len(points)} of {before} inside the Boston area since {start}")

    points = apply_privacy(points, cfg["privacy"], mode)
    photos_dir = ROOT / "data" / "photos" if args.photos and mode == "family" and not args.sample else None
    places = summarise(cluster(points, cfg["cluster_radius_m"]), cfg.get("place_names", {}), photos_dir)
    if mode == "public":
        # Snap pins to a ~110 m grid (after clustering, so places don't split)
        for p in places:
            p["lat"], p["lon"] = round(p["lat"], 3), round(p["lon"], 3)

    times = sorted(p["time"] for p in points if p["time"])
    data = {
        "meta": {
            "title": cfg["title"],
            "subtitle": cfg["subtitle"],
            "mode": mode,
            "sample": args.sample,
            "generated": datetime.now().isoformat(timespec="seconds"),
            "from": times[0][:10] if times else None,
            "to": times[-1][:10] if times else None,
            "n_points": len(points),
            "n_places": len(places),
            "n_areas": len({p["area"] for p in places}),
            "n_days": len({t[:10] for t in times}),
        },
        "places": places,
    }
    out = Path(args.out) if args.out else \
        ROOT / "web" / ("data.public.json" if mode == "public" else "data.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1))
    print(f"Wrote {out}: {len(places)} places across "
          f"{data['meta']['n_areas']} neighbourhoods ({mode} mode)")


if __name__ == "__main__":
    main()
