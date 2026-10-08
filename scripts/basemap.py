"""Build web/basemap.json, a lightweight vector basemap (land, water, neighborhoods).

Runs once; the output is committed. Needs: pip install shapely

Sources (public, on GitHub):
  - Boston neighborhoods, shoreline-clipped (Code for Germany "click_that_hood")
  - Massachusetts ZIP code tabulation areas (OpenDataDE, from US Census TIGER)

Trick: ZIP shapes cover land *and* water. Boston's own neighborhood shapes are clipped
to the shoreline, so (Boston ZIP area - Boston land) = the Charles River + harbor.
Land = all ZIP shapes - that water + Boston land.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
SOURCES = {
    "neighborhoods": "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/boston.geojson",
    "zips": "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/ma_massachusetts_zip_codes_geo.min.json",
}
VIEW = box(-71.20, 42.22, -70.90, 42.45)
SIMPLIFY = 0.00006  # ~6 m

# Places outside Boston worth naming on the map: (label, lat, lon, kind)
LABELS = [
    ("Charles River", 42.3565, -71.0905, "water"),
    ("Boston Harbor", 42.3480, -71.0280, "water"),
    ("Dorchester Bay", 42.3150, -71.0330, "water"),
    ("Cambridge", 42.3730, -71.1100, "town"),
    ("Brookline", 42.3330, -71.1300, "town"),
    ("Somerville", 42.3900, -71.0990, "town"),
]


def fetch(name: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{name}.json"
    if not f.exists():
        print(f"  downloading {name}…")
        urllib.request.urlretrieve(SOURCES[name], f)
    return json.loads(f.read_text())


def rounded(geom, nd=5):
    """GeoJSON geometry with coordinates rounded to keep the file small."""
    def r(c):
        return [r(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], nd), round(c[1], nd)]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def main():
    hoods = [(f["properties"]["name"], shape(f["geometry"]).buffer(0))
             for f in fetch("neighborhoods")["features"]]
    boston_land = unary_union([g for _, g in hoods])

    zips = [shape(f["geometry"]).buffer(0) for f in fetch("zips")["features"]]
    zips = [z for z in zips if z.intersects(VIEW)]
    # A ZIP counts as Boston when a good share of it is Boston land (the rest is river/harbor).
    in_boston = [z for z in zips if z.intersection(boston_land).area > 0.3 * z.area]
    water = unary_union(in_boston).difference(boston_land)
    land = unary_union(zips).difference(water).union(boston_land).intersection(VIEW)
    land = land.simplify(SIMPLIFY, preserve_topology=True)
    land = unary_union([p for p in getattr(land, "geoms", [land]) if p.area > 2e-7])

    out = {
        "attribution": "Neighborhoods: City of Boston via click_that_hood · ZIP areas: US Census TIGER via OpenDataDE",
        "land": rounded(land),
        "neighborhoods": [
            {"name": n, "geometry": rounded(g.simplify(SIMPLIFY, preserve_topology=True)),
             "label": [round(g.representative_point().y, 4), round(g.representative_point().x, 4)]}
            for n, g in hoods if g.intersects(VIEW) and n != "Harbor Islands"
        ],
        "labels": [{"text": t, "lat": la, "lon": lo, "kind": k} for t, la, lo, k in LABELS],
    }
    path = ROOT / "web" / "basemap.json"
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"Wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
