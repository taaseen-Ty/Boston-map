# My Boston, So Far

An interactive map of every place I've been since moving to Boston for grad school,
built from my own iPhone data: GPS metadata in my photos plus Google Maps Timeline visits.

**[Live demo →](https://YOUR-USERNAME.github.io/boston-map/)**

<!-- Add a screenshot once your real data is in: ![screenshot](screenshot.png) -->

## What it does

- Pulls location and time from photo EXIF data (HEIC/JPEG) and Google Maps Timeline exports
- Groups nearby points into "places" (about 120 m radius) and labels each with its neighborhood
- **Replay**: a timeline slider shows the map filling in day by day
- **Privacy by design**: raw exports never leave my laptop. The public build removes "hide zones"
  (e.g. home) and snaps every coordinate to a ~110 m grid

## How it works

```
data/photos/*.HEIC ─┐                         ┌─ web/data.json          (family, local only)
                    ├─ scripts/build.py ──────┤
data/timeline/*.json┘   filter → privacy →    └─ web/data.public.json   (published)
                        cluster → label
                                                  web/index.html (Leaflet) renders either
```

| File | Purpose |
|---|---|
| `scripts/sources.py` | Readers for photo EXIF GPS and the three Google Timeline export formats |
| `scripts/build.py` | Bounding-box/date filter, privacy zones, greedy distance clustering, summary stats |
| `scripts/neighborhoods.py` | Offline nearest-neighborhood labels (no geocoding API) |
| `config.json` | Title, start date, Boston bounding box, cluster radius, hide zones, name overrides |
| `web/index.html` | Single-file front end with no build step |

## Run it

```bash
pip install -r requirements.txt

python scripts/build.py --sample          # try it with demo data
python scripts/build.py                   # family version from your exports
python scripts/build.py --mode public     # resume-safe version

python -m http.server -d web 8000         # open http://localhost:8000
```

### Getting the data

1. **Photos**: in Photos on Mac, select your Boston photos → *File → Export → Export Unmodified
   Originals* → save into `data/photos/`.
2. **Timeline** (optional): Google Maps on iPhone → profile → *Your Timeline* → ⋯ →
   *Export Timeline data* → save the JSON into `data/timeline/`.
3. Set your home coordinates in `config.json → privacy.hide_zones`.
4. If a place gets the wrong name, rename it in `config.json → place_names`, e.g. `{"p004": "Mugar Library"}`.

## Deploy (GitHub Pages)

Settings → Pages → deploy from branch, folder `/web`. Pages only serves `data.public.json`;
`data.json` and everything in `data/` are gitignored.

## Stack

Python (Pillow, pillow-heif) · vanilla JS · Leaflet · CARTO basemap · GitHub Pages
