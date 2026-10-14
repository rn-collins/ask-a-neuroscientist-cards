#!/usr/bin/env python3
"""Tests for the release gate and for what the build writes.

Standard library only. Run from anywhere:

    python3 tests/test_release_gate.py

They work in the source repository and in the public edition: they read
data/releases.json and build into a temporary folder, never into dist/.
"""
import datetime
import importlib.util
import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build", ROOT / "scripts" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

ROWS = json.loads((ROOT / "data" / "releases.json").read_text())["pieces"]
INDEX_PAGES = {"plants", "places", "how-it-works", "everyday", "archive", "glossary", "ask", "questions", "inbox"}
DATES = sorted(r["releasedAt"] for r in ROWS if r["releasedAt"] and not r["hold"])


def build_into(tmp, day):
    """Run the real build for a date, into a temporary folder. Returns the folder."""
    old_argv, old_dist = sys.argv, build.DIST
    sys.argv = ["build.py", "--today", day.isoformat()]
    build.DIST = pathlib.Path(tmp) / "dist"
    try:
        build.main()
    finally:
        sys.argv, build.DIST = old_argv, old_dist
    return pathlib.Path(tmp) / "dist"


class Gate(unittest.TestCase):
    def test_boundaries(self):
        day = datetime.date(2026, 10, 13)
        row = lambda **k: {"slug": "x", "hold": False, "releasedAt": "2026-10-13", **k}
        self.assertTrue(build.is_released(row(), day))
        self.assertTrue(build.is_released(row(releasedAt="2026-10-12"), day))
        self.assertFalse(build.is_released(row(releasedAt="2026-10-14"), day))
        self.assertFalse(build.is_released(row(hold=True), day))
        self.assertFalse(build.is_released(row(releasedAt=""), day))
        self.assertFalse(build.is_released(None, day))
        self.assertFalse(build.is_released({"slug": "x", "releasedAt": "2026-10-01"}, day), "hold defaults to true")

    def test_release_rows(self):
        slugs = [r["slug"] for r in ROWS]
        self.assertEqual(len(slugs), len(set(slugs)), "duplicate slug")
        for r in ROWS:
            self.assertIsInstance(r["hold"], bool, r["slug"])
            if r["releasedAt"]:
                datetime.date.fromisoformat(r["releasedAt"])

    def test_every_row_has_its_files(self):
        for r in ROWS:
            self.assertTrue((ROOT / "cards" / f"{r['slug']}.html").exists(), f"card for {r['slug']}")
            self.assertTrue((ROOT / "content" / f"{r['slug']}.json").exists(), f"content for {r['slug']}")


class Output(unittest.TestCase):
    def check_day(self, day):
        with tempfile.TemporaryDirectory() as tmp:
            dist = build_into(tmp, day)
            released = {r["slug"] for r in ROWS if build.is_released(r, day)}
            built = {p.parent.name for p in dist.glob("*/index.html")}
            paths = {build.path_for(s) for s in released}
            # Every released piece has a page, and no other piece page exists.
            pieces = built - INDEX_PAGES
            self.assertEqual(pieces - paths, set(), f"pages for pieces that are not released ({day})")
            # The sitemap and the search index carry released pieces only.
            sitemap = (dist / "sitemap.xml").read_text()
            search = json.loads((dist / "search.json").read_text())
            self.assertEqual({s["s"] for s in search} - paths, set())
            for loc in re.findall(r"<loc>" + re.escape(build.BASE) + r"([^<]*)</loc>", sitemap):
                self.assertIn(loc.strip("/"), paths | INDEX_PAGES | {""}, f"sitemap lists {loc} ({day})")
            # Every internal link on every page lands on a page that was built:
            # previous, next, related, index and kicker links included.
            routes = {"/"} | {f"/{b}/" for b in built}
            for page in dist.rglob("index.html"):
                for href in re.findall(r'href="(/[\w./-]*)"', page.read_text()):
                    if href in ("/aan.css", "/favicon.ico") or href.endswith((".css", ".png", ".json", ".xml", ".txt")):
                        continue
                    self.assertIn(href, routes, f"{page.relative_to(dist)} links to {href} ({day})")
            # The redirects name released pieces only.
            for rule in json.loads((dist / "vercel.json").read_text())["redirects"]:
                self.assertIn(rule["destination"].strip("/"), paths)

    def test_day_before_first_release(self):
        if DATES:
            self.check_day(datetime.date.fromisoformat(DATES[0]) - datetime.timedelta(days=1))

    def test_first_release_day(self):
        if DATES:
            self.check_day(datetime.date.fromisoformat(DATES[0]))

    def test_latest_release_day(self):
        if DATES:
            self.check_day(datetime.date.fromisoformat(DATES[-1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
