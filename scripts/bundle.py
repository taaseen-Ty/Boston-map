"""Pack the map into ONE self-contained HTML file you can share.

    python scripts/build.py --photos     # family data with photo thumbnails
    python scripts/bundle.py             # -> dist/boston-map.html

The output has the data, basemap and Leaflet's CSS inlined (Leaflet's JS still loads
from cdnjs). It's what gets published as the shareable page.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAFLET_CSS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None, help="data file (default: web/data.json, else data.public.json)")
    ap.add_argument("--leaflet-css", default=None, help="local copy of leaflet.css (else downloaded)")
    ap.add_argument("--out", default=str(ROOT / "dist" / "boston-map.html"))
    ap.add_argument("--fragment", action="store_true",
                    help="omit <html>/<head>/<body> (for hosts that add their own skeleton)")
    args = ap.parse_args()

    web = ROOT / "web"
    data_file = Path(args.data) if args.data else (web / "data.json" if (web / "data.json").exists() else web / "data.public.json")
    data = json.loads(data_file.read_text())
    base = json.loads((web / "basemap.json").read_text())
    css = Path(args.leaflet_css).read_text() if args.leaflet_css else \
        urllib.request.urlopen(LEAFLET_CSS).read().decode()
    css = re.sub(r"url\([^)]*\)", "none", css)  # drop control images we don't use

    html = (web / "index.html").read_text()
    body = html.split("<!--BUNDLE:START-->")[1].split("<!--BUNDLE:END-->")[0]
    head, body = body.split('<!--BUNDLE:HEAD_END-->\n</head>\n<body>')
    head = re.sub(r'<link rel="stylesheet" href="[^"]*leaflet\.css"><!--LEAFLET_CSS-->',
                  lambda _: f"<style>{css}</style>", head)
    inline = ("<script>window.__DATA__=" + json.dumps(data, separators=(",", ":")) +
              ";window.__BASEMAP__=" + json.dumps(base, separators=(",", ":")) + ";</script>\n")
    body = body.replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet', inline +
                        '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet', 1)

    if args.fragment:
        body = head + body
    else:
        body = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + head + "</head>\n<body>\n" + body + "</body>\n</html>\n")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body)
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB) from {data_file.name}")


if __name__ == "__main__":
    main()
