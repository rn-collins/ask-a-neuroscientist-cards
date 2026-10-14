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


class Safety(unittest.TestCase):
    """The standard safety block is on every page, and a hazard warning comes
    before the text it warns about. Pieces held back for a later date are
    covered too: the release record is read as if every piece were released,
    in memory only, so data/releases.json is never touched."""

    PHRASE = "Education, not medical advice."
    ASIDE = re.compile(r'<aside class="safety".*?</aside>', re.S)

    def build_all(self, tmp):
        """Build every piece (as of a far-off date). Returns the dist folder."""
        real = build.load_releases
        every = lambda: {s: {**e, "hold": False, "releasedAt": "2028-12-31"} for s, e in real().items()}
        build.load_releases = every
        try:
            dist = build_into(tmp, datetime.date(2028, 12, 31))
        finally:
            build.load_releases = real
        return dist

    def pages(self, dist):
        return {"/" + str(p.relative_to(dist)): p.read_text() for p in dist.rglob("index.html")}

    def test_every_page_has_the_block_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = self.build_all(tmp)
            pages = self.pages(dist)
            self.assertTrue(any(k.split("/")[1] not in INDEX_PAGES for k in pages), "expected piece pages to be built")
            key_built = "/warning-key/index.html" in pages
            for path, page in pages.items():
                blocks = self.ASIDE.findall(page)
                self.assertEqual(len(blocks), 1, f"{path}: safety block count")
                block = blocks[0]
                for need in (self.PHRASE, "call 911", "1-800-222-1222"):
                    self.assertIn(need, block, f"{path}: {need}")
                self.assertEqual('href="/warning-key/"' in block, key_built, f"{path}: warning key link")
                # In the footer, after everything else on the page.
                self.assertLess(page.index("<footer"), page.index('<aside class="safety"'), path)
                self.assertGreater(page.index("</footer>"), page.index("</aside>"), path)
            if any(build.path_for(f.stem) == "warning-key" for f in (ROOT / "content").glob("*.json")):
                self.assertTrue(key_built, "the warning key page is part of the series")

    def test_hazard_warning_is_above_the_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = self.build_all(tmp)
            seen = 0
            for f in sorted((ROOT / "content").glob("*.json")):
                c = json.loads(f.read_text())
                page_file = dist / build.path_for(f.stem) / "index.html"
                if not c.get("warning") or not page_file.exists():
                    continue
                page = page_file.read_text()
                if '<main class="reader" id="read">' not in page:
                    continue  # the address belongs to an index page (aan-ask and /ask/)
                seen += 1
                self.assertEqual(page.count('<div class="warn"'), 1, f.stem)
                at = page.index('<div class="warn"')
                self.assertIn(build.esc(c["warning"]), page[at:page.index("</div>", at)], f.stem)
                self.assertGreater(at, page.index("</h1>"), f"{f.stem}: warning before the title")
                if c.get("body"):
                    first = page.index("<p>" + build.esc(c["body"][0]) + "</p>")
                    self.assertLess(at, first, f"{f.stem}: warning is below the body text")
            # Every piece with a warning (the series furniture templates are never built).
            want = [f for f in (ROOT / "content").glob("*.json")
                    if not f.stem.startswith("_") and build.path_for(f.stem) not in INDEX_PAGES
                    and json.loads(f.read_text()).get("warning") and json.loads(f.read_text()).get("role") != "template"]
            self.assertEqual(seen, len(want), "pieces with a warning that were not checked")

    def test_every_piece_is_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = self.build_all(tmp)
            built = {p.parent.name for p in dist.glob("*/index.html")} - INDEX_PAGES
            # Templates are never built. A piece whose address an index page also uses
            # (aan-ask and /ask/) is left to that page, which carries the block too.
            want = {build.path_for(f.stem) for f in (ROOT / "content").glob("*.json")
                    if not f.stem.startswith("_") and json.loads(f.read_text()).get("role") != "template"} - INDEX_PAGES
            self.assertEqual(want - built, set(), "pieces the safety check did not see")
            self.assertGreaterEqual(len(want), 1)

    def test_key_link_follows_the_key_page(self):
        # Before the warning key is released its page does not exist, so nothing may link to it.
        key = next((r["releasedAt"] for r in ROWS if build.path_for(r["slug"]) == "warning-key" and r["releasedAt"] and not r["hold"]), None)
        if key is None:
            self.skipTest("the warning key is not part of this edition")
        before = datetime.date.fromisoformat(key) - datetime.timedelta(days=1)
        with tempfile.TemporaryDirectory() as tmp:
            dist = build_into(tmp, before)
            self.assertFalse((dist / "warning-key").exists())
            for page in dist.rglob("index.html"):
                self.assertNotIn('href="/warning-key/"', page.read_text(), str(page))
                self.assertEqual(len(self.ASIDE.findall(page.read_text())), 1, str(page))
        with tempfile.TemporaryDirectory() as tmp:
            dist = build_into(tmp, datetime.date.fromisoformat(key))
            for page in dist.rglob("index.html"):
                self.assertIn('href="/warning-key/"', self.ASIDE.search(page.read_text()).group(0), str(page))

    def test_the_check_catches_a_missing_block_or_a_misplaced_warning(self):
        content = {"aan-x": {"slug": "aan-x", "title": "T", "body": ["First para."], "warning": "Careful."}}
        build.LIVE_PAGES.clear()
        block = build.safety_block()
        good = '<main class="reader" id="read"><h1>T</h1><div class="warn" role="note"><b>Before you go further</b>Careful.</div><p>First para.</p>' \
            '<footer class="foot">' + block + "</footer>"
        pages = {"/x/index.html": good}
        self.assertEqual(build.safety_problems(pages, content), [])
        self.assertTrue(build.safety_problems({"/x/index.html": good.replace(block, "")}, content))
        self.assertTrue(build.safety_problems({"/x/index.html": good.replace("</footer>", block + "</footer>")}, content))
        below = '<main class="reader" id="read"><h1>T</h1><p>First para.</p><div class="warn">Careful.</div>' + good[good.index("<footer"):]
        self.assertTrue(build.safety_problems({"/x/index.html": below}, content))
        self.assertTrue(build.safety_problems({"/x/index.html": good.replace("1-800-222-1222", "")}, content))
        build.LIVE_PAGES.add(build.KEY_PATH)
        try:
            self.assertTrue(build.safety_problems(pages, content), "key page built but not linked")
        finally:
            build.LIVE_PAGES.clear()


class Addresses(unittest.TestCase):
    """A card never publishes at an address an index page uses, and a card with its
    own body class (the dark cards) still gets the reader class. Every piece is built,
    in memory only, as in the Safety tests."""

    def build_all(self, tmp):
        real = build.load_releases
        every = lambda: {s: {**e, "hold": False, "releasedAt": "2028-12-31"} for s, e in real().items()}
        build.load_releases = every
        try:
            return build_into(tmp, datetime.date(2028, 12, 31))
        finally:
            build.load_releases = real

    def test_the_reserved_paths_match_the_index_pages(self):
        self.assertEqual(build.RESERVED_PATHS, INDEX_PAGES)

    def test_no_card_takes_an_index_address(self):
        for f in (ROOT / "content").glob("*.json"):
            self.assertNotIn(build.path_for(f.stem), INDEX_PAGES, f.stem)
        for short in build.RESERVED_PATHS:
            self.assertEqual(build.path_for("aan-" + short), "aan-" + short, short)
            self.assertEqual(build.path_for("arc-" + short), "arc-" + short, short)
        self.assertEqual(build.path_for("aan-sample"), "sample")
        self.assertEqual(build.path_for("arc-sample"), "sample")
        self.assertEqual(build.path_for("plain"), "plain")

    def test_the_question_page_is_not_overwritten_by_a_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = self.build_all(tmp)
            ask = (dist / "ask" / "index.html").read_text()
            self.assertIn('id="askform"', ask)
            # A card whose short path is a reserved address is built at its full slug.
            for f in (ROOT / "content").glob("*.json"):
                if f.stem.startswith(("aan-", "arc-")) and f.stem[4:] in build.RESERVED_PATHS:
                    card = (dist / f.stem / "index.html").read_text()
                    self.assertIn('<main class="reader" id="read">', card, f.stem)

    def test_every_card_page_has_the_reader_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = self.build_all(tmp)
            seen = dark = 0
            for page_file in dist.rglob("index.html"):
                page = page_file.read_text()
                if '<main class="reader" id="read">' not in page:
                    continue
                body = re.search(r"<body[^>]*>", page).group(0)
                self.assertIn("reader-page", body, str(page_file.relative_to(dist)))
                seen += 1
                dark += "dark" in body
            self.assertGreater(seen, 0)
            self.assertGreater(dark, 0, "expected the dark cards to keep their own class")

    def test_add_reader_class(self):
        self.assertEqual(build.add_reader_class("<body>"), '<body class="reader-page">')
        self.assertEqual(build.add_reader_class('<body class="dark">'), '<body class="dark reader-page">')
        self.assertEqual(build.add_reader_class('<body class="a b" data-x="1">'), '<body class="a b reader-page" data-x="1">')


if __name__ == "__main__":
    unittest.main(verbosity=2)
