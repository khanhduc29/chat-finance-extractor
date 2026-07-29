"""
Render the Flask app's routes into static, self-contained HTML files under
docs/, so the demo can be hosted with GitHub Pages / Vercel static hosting
(no Python/Flask server needed at request time for the HTML — only
/api/ask, which Vercel serves separately as a Python serverless function
from api/ask.py).

Pages exported:
  - /            -> docs/index.html      (group list)
  - /g/<slug>    -> docs/g-<slug>.html   (one per group in app.GROUPS)
  - /stats       -> docs/stats.html

Usage:
    python build_static_demo.py

Re-run this after transactions/data change, or whenever app.GROUPS changes
(adding/removing a group), to refresh the frozen snapshot.
"""
from pathlib import Path

from app import GROUPS, app

OUT_DIR = Path(__file__).parent / "docs"

# Flask route -> static filename.
PAGES = {"/": "index.html", "/stats": "stats.html"}
for g in GROUPS:
    PAGES[f"/g/{g['slug']}"] = f"g-{g['slug']}.html"

# Applied as plain (exact) substring replacements on href="..." attributes —
# safe because each route string is distinct enough not to appear as a
# substring of another (e.g. href="/" never matches inside href="/g/x").
LINK_FIXUPS = [(f'href="{route}"', f'href="{filename}"') for route, filename in PAGES.items()]


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
