"""
Render the Flask app's two routes (/ and /stats) into static, self-contained
HTML files under docs/, so the demo can be hosted with GitHub Pages (no
Python/Flask server needed at request time).

Usage:
    python build_static_demo.py

Re-run this after transactions.json / zalo_thu_chi_data.json changes to
refresh the frozen snapshot served by GitHub Pages.
"""
from pathlib import Path

from app import app

OUT_DIR = Path(__file__).parent / "docs"

PAGES = {
    "/": "index.html",
    "/stats": "stats.html",
}

LINK_FIXUPS = [
    ('href="/stats"', 'href="stats.html"'),
    ('href="/"', 'href="index.html"'),
]


def main():
    OUT_DIR.mkdir(exist_ok=True)
    client = app.test_client()

    for route, filename in PAGES.items():
        resp = client.get(route)
        if resp.status_code != 200:
            raise RuntimeError(f"{route} returned {resp.status_code}")
        html = resp.get_data(as_text=True)
        for old, new in LINK_FIXUPS:
            html = html.replace(old, new)
        (OUT_DIR / filename).write_text(html, encoding="utf-8")
        print(f"wrote docs/{filename} ({len(html):,} bytes)")

    (OUT_DIR / ".nojekyll").touch()
    print("done")


if __name__ == "__main__":
    main()
