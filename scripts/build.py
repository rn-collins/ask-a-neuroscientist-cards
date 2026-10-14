#!/usr/bin/env python3
"""Build the Ask a Neuroscientist site.

Each card in cards/ is the animated post graphic, exactly as it is recorded for
social. This script keeps that card as the hero of its page and adds the reader
layer underneath it from content/<slug>.json: the explanation, the warning, the
sources and where to go next. It also writes the index pages, the search index,
the sitemap and a link-preview image per card.

    python3 scripts/build.py            # build into dist/
    python3 scripts/build.py --check    # report problems, write nothing
    python3 scripts/build.py --today 2026-10-18   # preview the site as of a date
    python3 scripts/build.py --check --today 2028-12-31   # check every piece, released or not

Every page carries the standard safety block (safety_block) and a piece's hazard
warning stands above its text; safety_problems fails the build if either is not
so, with or without --check.

What is public is decided by data/releases.json and nothing else. A piece is
built only when its releasedAt date (Pacific/Honolulu) is today or earlier and
its hold is false. Every other piece is left out of everything: its page, the
indexes, the search index, the sitemap, the redirects and its preview image,
so its address returns 404. The source files stay where they are.
"""
import datetime
import html
import json
import pathlib
import re
import shutil
import sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
CONTENT = ROOT / "content"
DIST = ROOT / "dist"
RELEASES = ROOT / "data" / "releases.json"
TZ = ZoneInfo("Pacific/Honolulu")
BASE = "https://rn-ask-a-neuroscientist.vercel.app"
SERIES = "Ask a Neuroscientist"

KIND_LABEL = {
    "plant": "Plants",
    "place": "Place by place",
    "receptor": "How it works",
    "term": "Glossary",
    "myth": "Myth or mechanism",
    "daily-life": "Everyday brain",
    "series": "About the series",
    "archive": "From the Fat Nugs archive",
}
KIND_ORDER = ["plant", "place", "receptor", "myth", "daily-life", "archive", "term", "series"]

# The card pages size the stage to the viewport because they were built to be
# recorded full screen. On a reader page the stage sits in a column with an
# article under it, so it scales to its container instead.
FIT_OLD = re.compile(r"function fit\(\)\{const s=Math\.min\(innerWidth/540,innerHeight/675\);st\.style\.transform='scale\('\+s\+'\)'\}")
FIT_NEW = (
    "function fit(){const c=st.parentElement,"
    "s=Math.min(c.clientWidth/540,1);"
    "st.style.transform='scale('+s+')';"
    "st.style.transformOrigin='top left';"
    "c.style.height=(675*s)+'px'}"
)


# Addresses the index, question and inbox pages use. A card never publishes at one of these:
# a card stored as aan-ask would otherwise be overwritten by the question page at /ask/.
RESERVED_PATHS = {"ask", "questions", "inbox", "archive", "plants", "places", "how-it-works", "glossary", "everyday"}


def path_for(slug):
    """The published path for a card. Cards are stored as aan-awa and arc-coa;
    they publish at /awa/ and /coa/, because these links get pasted into
    captions. The stored paths redirect. A card whose short path is one of the
    RESERVED_PATHS keeps its full stored slug (aan-ask publishes at /aan-ask/)."""
    for prefix in ("aan-", "arc-"):
        if slug.startswith(prefix):
            short = slug[len(prefix):]
            return slug if short in RESERVED_PATHS else short
    return slug


def esc(s):
    return html.escape(s or "", quote=True)


def load_content():
    """Card content, keyed by card slug. Each page is published at a short path
    (aan-awa is served at /awa/), with the original path redirecting, because
    these links get pasted into captions."""
    out = {}
    for f in sorted(CONTENT.glob("*.json")):
        if f.stem.startswith("_"):
            continue
        try:
            out[f.stem] = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            print(f"  BROKEN JSON {f.name}: {e}")
    return out


def today_hst():
    """Today's date in Hawaiʻi, or the date given with --today for a preview."""
    if "--today" in sys.argv:
        return datetime.date.fromisoformat(sys.argv[sys.argv.index("--today") + 1])
    return datetime.datetime.now(TZ).date()


def load_releases():
    """The release record, keyed by card slug."""
    doc = json.loads(RELEASES.read_text())
    return {e["slug"]: e for e in doc["pieces"]}


# Text that marks a piece as unfinished. A piece carrying any of it is never
# built, whatever its release record says (RN, Oct 13, 2026: the reader
# question template must never be public with its placeholders).
PLACEHOLDER = re.compile(r"goes here|lorem ipsum|\bTODO\b|\bTBD\b|placeholder|\[truncated\]", re.I)


def unfinished(slug, c):
    """Why a piece must not be built even when its date has come, or None."""
    if c.get("role") == "template":
        return "it is a template"
    raw = card_html(slug) or ""
    stage = raw.split('<div class="stage">', 1)[-1].split("<script>", 1)[0]
    if PLACEHOLDER.search(stage) or PLACEHOLDER.search(json.dumps(c, ensure_ascii=False)):
        return "it still has placeholder text"
    return None


def is_released(entry, today):
    if not entry or entry.get("hold", True):
        return False
    when = (entry.get("releasedAt") or "").strip()
    if not when:
        return False
    return datetime.date.fromisoformat(when) <= today


def released_order(content, releases):
    """Released pieces in the order they came out, oldest first, so each page
    can point at the one before it and the one after it."""
    return sorted(content, key=lambda s: (releases[s]["releasedAt"], content[s]["title"].lower()))


def card_html(slug):
    p = CARDS / f"{slug}.html"
    return p.read_text() if p.exists() else None


# The index pages, the kinds each one lists, and their names. An index is
# built, linked and listed in the sitemap only when it has a released piece.
INDEXES = [
    ("/plants/", ["plant"], "Plants", "What each plant's active compound does in the brain, and what it does not."),
    ("/places/", ["place"], "Place by place", "Where these plants are traditional, legal, restricted or still federally illegal."),
    ("/how-it-works/", ["receptor", "myth"], "How it works", "Receptor families, the brain map, and myths checked against mechanisms."),
    ("/glossary/", ["term"], "Glossary", "Receptor, agonist, antagonist, reuptake, MAO inhibitor, in plain language."),
    ("/everyday/", ["daily-life"], "Everyday brain", "Sleep, memory, habits, grief, focus and the research behind them."),
]
NAV = [("/plants/", "Plants"), ("/places/", "Places"), ("/how-it-works/", "How it works"),
       ("/everyday/", "Everyday"), ("/archive/", "Archive"), ("/glossary/", "Glossary")]
# Filled in by main() with the index paths that have at least one released piece.
LIVE_INDEXES = set()

# The standard safety block (see safety_block). The warning key is a piece like
# any other, so its page exists only from its release date; the block links to
# it from that day on and never before, so the link can not land on a 404.
SAFETY_PHRASE = "Education, not medical advice."
POISON_HELP = "1-800-222-1222"
KEY_PATH = "/warning-key/"
# Filled in by main(): the page paths (here only the key) that are built.
LIVE_PAGES = set()


def kind_index(kind):
    """The index page that lists a kind, if that index is built."""
    if kind == "archive":
        path = "/archive/"
    else:
        path = next((p for p, kinds, _, _ in INDEXES if kind in kinds), None)
    return path if path in LIVE_INDEXES else None


def sitebar():
    links = "".join(f'<a href="{p}">{esc(n)}</a>' for p, n in NAV if p in LIVE_INDEXES)
    return (
        '<header class="sitebar"><a class="wordmark" href="/">Ask a Neuroscientist</a>'
        f'<nav>{links}<a href="/questions/">Ask a question</a></nav></header>'
    )


def safety_block():
    """The standard safety block, written on every page of the site.

    One block, one wording, in the footer of every page the build writes:
    the series is education, the emergency number, the Poison Help number,
    and a link to the warning key, the page that explains the series'
    warnings. build.py and the tests fail when a page lacks it."""
    key = f' <a href="{KEY_PATH}">What the warnings in this series mean</a>.' if KEY_PATH in LIVE_PAGES else ""
    return (
        '<aside class="safety" aria-labelledby="safety-title"><h2 id="safety-title">Safety</h2>'
        f"<p><strong>{SAFETY_PHRASE}</strong> In an emergency, call 911. "
        f'For a possible poisoning in the US, call Poison Help at <a href="tel:{POISON_HELP.replace("-", "")}">{POISON_HELP}</a>.'
        f"{key}</p></aside>"
    )


def footer():
    return (
        '<footer class="foot">' + safety_block() + '<p>Ask a Neuroscientist is written by RN Collins. '
        'The series began at <i>Fat Nugs Magazine</i>. Nothing here is legal advice. '
        'Talk to a clinician about your own health, and check the law where you live.</p></footer>'
    )


def ask_block(title, page="/"):
    """The question form.

    It posts to /api/question, which stores the question in the project's own
    blob store. It reads as a comment card (RN, Oct 13, 2026): questions shape
    what gets made, no reply is promised, and credit is offered only to readers
    who leave handles and tick the box. The page address travels with it so an answer can point back at
    what prompted it. Without JavaScript the form still submits and the
    function replies with a plain page.
    """
    where = esc(title.lower())
    return (
        '<section class="ask"><form id="askform" action="/api/question" method="post">'
        f'<label for="q">Ask a question about {where}</label>'
        '<textarea id="q" name="question" required minlength="10" maxlength="2000" '
        'placeholder="What do you want to know?"></textarea>'
        '<label for="qn" class="opt">First name or nickname (optional)</label>'
        '<input id="qn" type="text" name="name" maxlength="80" autocomplete="nickname" placeholder="Optional">'
        '<label for="qh" class="opt">Your handles: Instagram, TikTok, Threads, YouTube or other (optional)</label>'
        '<input id="qh" type="text" name="handles" maxlength="200" placeholder="@you on Instagram, @you on TikTok">'
        '<label class="opt check"><input type="checkbox" name="credit" value="yes"> '
        'OK to credit me by name or handle if I use this</label>'
        f'<input type="hidden" name="page" value="{esc(page)}">'
        '<input type="hidden" name="from" id="askfrom" value="">'
        '<div class="hp" aria-hidden="true"><label>Leave this empty'
        '<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>'
        '<button type="submit">Send the question</button>'
        '<p class="note" id="asknote">Think of this as a comment card. I can\'t reply to each question, '
        'and I can\'t promise to credit you. If you\'d like a shout-out if your question is used, leave your '
        'handles above and tick the box, and I\'ll try. Please leave out personal medical details. '
        'This is education, not medical advice.</p></form></section>'
        '<script>(function(){var f=document.getElementById("askform");if(!f)return;'
        'var src=new URLSearchParams(location.search).get("from");'
        'if(src){var h=document.getElementById("askfrom");if(h)h.value=src.slice(0,60)}'
        'var n=document.getElementById("asknote"),b=f.querySelector("button");'
        'f.addEventListener("submit",function(e){e.preventDefault();'
        'var d=Object.fromEntries(new FormData(f).entries());'
        'b.disabled=true;b.textContent="Sending";'
        'fetch("/api/question",{method:"POST",headers:{"content-type":"application/json"},'
        'body:JSON.stringify(d)}).then(function(r){return r.json()}).then(function(j){'
        'if(j.ok){f.innerHTML=\'<p><b>Thank you, your question is in.</b> It helps decide what I make next. '
        'I can\\\'t reply to each one.</p>\'}else{b.disabled=false;b.textContent="Send the question";'
        'n.textContent=j.error||"That did not send. Please try again."}})'
        '.catch(function(){b.disabled=false;b.textContent="Send the question";'
        'n.textContent="That did not send. Please try again."})})})();</script>'
    )


def piece_links(slug, content, releases, order, today):
    """Where this piece lives elsewhere, and the way through the gallery.
    A second sources page is linked only once its own date has come."""
    r = releases[slug]
    rows = []
    for i, u in enumerate(r.get("postUrls") or []):
        rows.append(f'<li>The post{"" if i == 0 else " " + str(i + 1)}: <a href="{esc(u)}" rel="noreferrer">{esc(u)}</a></li>')
    if r.get("sourcePageUrl"):
        rows.append(f'<li>Sources page: <a href="{esc(r["sourcePageUrl"])}">{esc(r["sourcePageUrl"])}</a></li>')
    for o in r.get("otherSourcePages") or []:
        if is_released({"hold": False, "releasedAt": o.get("releasedAt")}, today):
            rows.append(f'<li>Also on: <a href="{esc(o["url"])}">{esc(o["url"])}</a></li>')
    if r.get("longFormUrl"):
        rows.append(f'<li>Full article: <a href="{esc(r["longFormUrl"])}" rel="noreferrer">{esc(r["longFormUrl"])}</a></li>')
    i = order.index(slug)
    nav = ['<a href="/">All pieces</a>']
    if i > 0:
        p = order[i - 1]
        nav.append(f'<a href="/{esc(path_for(p))}/" rel="prev">Previous: {esc(content[p]["title"])}</a>')
    if i < len(order) - 1:
        n = order[i + 1]
        nav.append(f'<a href="/{esc(path_for(n))}/" rel="next">Next: {esc(content[n]["title"])}</a>')
    out = ""
    if rows:
        out += '<h2>This piece elsewhere</h2><ul class="elsewhere">' + "".join(rows) + "</ul>"
    out += '<nav class="pager" aria-label="Gallery">' + "".join(nav) + "</nav>"
    return out


def reader_html(c, content, releases, order, today):
    slug = c["slug"]
    parts = [f'<main class="reader" id="read">']
    label = esc(KIND_LABEL.get(c.get("kind"), SERIES))
    where = kind_index(c.get("kind"))
    parts.append(f'<p class="kicker"><a href="{where}">{label}</a></p>' if where else f'<p class="kicker">{label}</p>')
    parts.append(f'<h1>{esc(c["title"])}</h1>')
    if c.get("dek"):
        parts.append(f'<p class="dek">{esc(c["dek"])}</p>')
    if c.get("original"):
        o = c["original"]
        parts.append(
            f'<p class="origin">First published as <a href="{esc(o["url"])}" rel="noreferrer">'
            f'{esc(o["title"])}</a> in <i>{esc(o["publication"])}</i>, {esc(o["date"])}.</p>'
        )
    # A hazard warning comes before the text it warns about, not after it.
    if c.get("warning"):
        parts.append(f'<div class="warn" role="note"><b>Before you go further</b>{esc(c["warning"])}</div>')
    for para in c.get("body", []):
        parts.append(f"<p>{esc(para)}</p>")
    if c.get("sources"):
        parts.append("<h2>Sources</h2><ol class=\"sources\">")
        for s in c["sources"]:
            bits = ", ".join(x for x in [s.get("publisher"), s.get("date")] if x)
            parts.append(
                f'<li><div><a href="{esc(s["url"])}" rel="noreferrer">{esc(s["title"])}</a>'
                + (f" <span>({esc(bits)})</span>" if bits else "")
                + (f'<span class="what">{esc(s.get("supports", ""))}</span>' if s.get("supports") else "")
                + "</div></li>"
            )
        parts.append("</ol>")
    rel = [r for r in c.get("related", []) if r in content and r != slug]
    if rel:
        parts.append('<h2>Where to go next</h2><div class="related">')
        for r in rel[:5]:
            o = content[r]
            parts.append(
                f'<a href="/{esc(path_for(r))}/"><b>{esc(o["title"])}</b>'
                f'<small>{esc(KIND_LABEL.get(o.get("kind"), ""))}</small></a>'
            )
        parts.append("</div>")
    parts.append(piece_links(slug, content, releases, order, today))
    parts.append(ask_block(c["title"], f"/{path_for(slug)}/"))
    parts.append("</main>")
    return "".join(parts)


def head_tags(c):
    slug = c["slug"]
    url = f"{BASE}/{path_for(slug)}/"
    img = f"{BASE}/og/{slug}.png"
    desc = c.get("dek") or c["title"]
    return (
        f'<link rel="canonical" href="{esc(url)}">'
        f'<meta property="og:url" content="{esc(url)}">'
        f'<meta property="og:type" content="article">'
        f'<meta property="og:site_name" content="{SERIES}">'
        f'<meta property="og:title" content="{esc(c["title"])}">'
        f'<meta property="og:description" content="{esc(desc)}">'
        f'<meta property="og:image" content="{esc(img)}">'
        f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
        f'<meta name="twitter:card" content="summary_large_image">'
        f'<meta name="twitter:image" content="{esc(img)}">'
        f'<link rel="stylesheet" href="/aan.css">'
    )


def add_reader_class(page):
    """Mark the page as a reader page. A card may already carry its own body class
    (the dark cards), so the class is added to it, never replaced or skipped."""
    def fix(m):
        attrs = m.group(1) or ""
        if 'class="' in attrs:
            return "<body" + re.sub(r'class="([^"]*)"', lambda c: f'class="{c.group(1)} reader-page"', attrs, count=1) + ">"
        return f'<body class="reader-page"{attrs}>'
    return re.sub(r"<body((?:\s[^>]*)?)>", fix, page, count=1)


def build_card(slug, c, content, releases, order, today):
    raw = card_html(slug)
    if raw is None:
        return None, f"no card markup for {slug}"
    page = raw
    page = page.replace('<meta name="robots" content="noindex,nofollow">', "")
    page = re.sub(r"<title>[^<]*</title>", f"<title>{esc(c['title'])} · {SERIES}</title>", page, count=1)
    page = re.sub(r'<meta name="description"[^>]*>', "", page)
    page = page.replace(
        "</head>",
        f'<meta name="description" content="{esc(c.get("dek") or c["title"])}">' + head_tags(c) + "</head>",
        1,
    )
    page, n = FIT_OLD.subn(FIT_NEW, page)
    page = add_reader_class(page)
    page = page.replace('<div class="stage">', sitebar() + '<div class="hero"><div class="stage">', 1)
    page = page.replace("</div><script>", "</div></div>" + reader_html(c, content, releases, order, today) + footer() + "<script>", 1)
    note = None if n else f"{slug}: stage scaling not patched"
    return page, note


def page_shell(title, desc, body, path):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title) if title == SERIES else esc(title) + " · " + SERIES}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE}{path}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{BASE}{path}"><meta property="og:image" content="{BASE}/og/_site.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{BASE}/og/_site.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=DM+Sans:opsz,wght@9..40,400..700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/aan.css"></head><body>{sitebar()}{body}{footer()}</body></html>"""


def card_list(items, content):
    out = ['<div class="cards">']
    for slug in items:
        c = content[slug]
        out.append(
            f'<a href="/{esc(path_for(slug))}/"><b>{esc(c["title"])}</b><span>{esc(c.get("dek", ""))}</span></a>'
        )
    out.append("</div>")
    return "".join(out)


def build_indexes(content):
    pages = {}
    by_kind = {}
    for slug, c in sorted(content.items(), key=lambda kv: kv[1]["title"].lower()):
        by_kind.setdefault(c.get("kind", "series"), []).append(slug)

    head = (
        '<div class="index-head"><h1>Ask a Neuroscientist</h1>'
        "<p>How plants, places and daily life act on the brain. Every page explains the mechanism, "
        "names its sources, and says what the evidence does not settle.</p></div>"
        '<div class="search"><label for="s" class="visually-hidden"></label>'
        '<input id="s" type="search" placeholder="Search plants, receptors, places, myths" autocomplete="off"></div>'
        '<div id="results"></div><div id="browse">'
    )
    body = [head]
    for kind in KIND_ORDER:
        if kind in by_kind:
            body.append(f'<h2 class="group-title">{KIND_LABEL[kind]}</h2>')
            body.append(card_list(by_kind[kind], content))
    body.append("</div>")
    body.append(
        '<script>(function(){var q=document.getElementById("s"),r=document.getElementById("results"),'
        'b=document.getElementById("browse"),idx=null;'
        'q.addEventListener("input",async function(){var v=q.value.trim().toLowerCase();'
        'if(!v){r.innerHTML="";b.hidden=false;return}'
        'if(!idx){idx=await fetch("/search.json").then(function(x){return x.json()})}'
        'var hits=idx.filter(function(c){return (c.t+" "+c.d+" "+c.g).toLowerCase().indexOf(v)>-1}).slice(0,40);'
        'b.hidden=true;r.innerHTML=hits.length?\'<div class="cards">\'+hits.map(function(c){'
        'return \'<a href="/\'+c.s+\'/"><b>\'+c.t+\'</b><span>\'+c.d+\'</span></a>\'}).join("")+"</div>"'
        ':\'<p class="empty">Nothing matches that yet.</p>\'})})();</script>'
    )
    pages["/index.html"] = page_shell(
        "Ask a Neuroscientist",
        "How plants, places and daily life act on the brain, with the mechanism and the sources for each.",
        "".join(body),
        "/",
    )

    for path, kinds, title, desc in INDEXES:
        items = [s for k in kinds for s in by_kind.get(k, [])]
        if not items:
            continue
        body = f'<div class="index-head"><h1>{esc(title)}</h1><p>{esc(desc)}</p></div>' + card_list(items, content)
        pages[path + "index.html"] = page_shell(title, desc, body, path)

    archive = [s for s, c in content.items() if c.get("original")]
    if archive:
        def when(slug):
            d = content[slug]["original"].get("date", "")
            m = re.match(r"(\d{1,2}) (\w+) (\d{4})", d)
            months = ["January", "February", "March", "April", "May", "June", "July",
                      "August", "September", "October", "November", "December"]
            if m and m.group(2) in months:
                return (int(m.group(3)), months.index(m.group(2)) + 1, int(m.group(1)))
            return (0, 0, 0)
        archive.sort(key=when, reverse=True)
        rows = ['<div class="cards">']
        for slug in archive:
            c = content[slug]
            rows.append(
                f'<a href="/{esc(path_for(slug))}/"><b>{esc(c["title"])}</b>'
                f'<span>{esc(c.get("dek", ""))}</span>'
                f'<span class="when">{esc(c["original"].get("date", ""))}</span></a>'
            )
        rows.append("</div>")
        pages["/archive/index.html"] = page_shell(
            "The Fat Nugs archive",
            "Pieces RN Collins wrote for Fat Nugs Magazine, each with what it found and a link to the original.",
            '<div class="index-head"><h1>The Fat Nugs archive</h1><p>Pieces RN wrote for '
            '<i>Fat Nugs Magazine</i>, newest first. Each page carries what the piece found, its sources, '
            'and a link to the original. More are added as they are posted.</p></div>' + "".join(rows),
            "/archive/",
        )

    qbody = (
        '<div class="index-head"><h1>Got a question about your brain?</h1>'
        "<p>Think of this as a comment card. Every question is read and taken into account, and what people "
        "actually wonder about decides what I make next: posts, videos and long-form writing.</p></div>"
        '<div class="reader">' + ask_block("the brain", "/questions/") + "</div>"
    )
    pages["/ask/index.html"] = page_shell(
        "Ask a question", "Send a question about plants, sleep, focus or how the brain handles stress.", qbody, "/ask/"
    )
    pages["/questions/index.html"] = page_shell(
        "Ask a question", "Send a question about plants, sleep, focus or how the brain handles stress.", qbody, "/questions/"
    )
    return pages


def build_inbox():
    """The page where RN reads what readers have sent.

    No third party is involved: the questions sit in the project's own store,
    and this page asks /api/inbox for them with the passphrase held in the
    project environment. It is unlisted and unindexed.
    """
    body = (
        '<div class="index-head"><h1>Questions</h1>'
        '<p>What readers have sent, newest first. The passphrase is held in the project '
        'settings, not on this page.</p></div>'
        '<div class="reader"><form id="inbox" class="ask">'
        '<label for="pp">Passphrase</label>'
        '<input id="pp" type="password" name="passphrase" autocomplete="current-password" required>'
        '<button type="submit">Open</button>'
        '<p class="note" id="innote"></p></form><div id="list"></div></div>'
        '<script>(function(){'
        'var f=document.getElementById("inbox"),n=document.getElementById("innote"),'
        'l=document.getElementById("list"),b=f.querySelector("button");'
        'function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){'
        'return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]})}'
        'f.addEventListener("submit",function(e){e.preventDefault();b.disabled=true;n.textContent="Opening";'
        'fetch("/api/inbox",{method:"POST",headers:{"content-type":"application/json"},'
        'body:JSON.stringify({passphrase:document.getElementById("pp").value})})'
        '.then(function(r){return r.json()}).then(function(j){b.disabled=false;'
        'if(!j.ok){n.textContent=j.error||"That did not work.";return}'
        'n.textContent=j.count+" question"+(j.count===1?"":"s")+".";'
        'l.innerHTML=j.questions.map(function(q){'
        'return "<article style=\'border-top:1px solid var(--r-line);padding:1rem 0\'>"'
        '+"<p style=\'color:var(--r-soft);font-size:.875rem;margin-bottom:.35rem\'>"'
        '+esc((q.receivedAt||"").replace("T"," ").slice(0,16))'
        '+(q.from?" · from "+esc(q.from):"")+(q.page?" · "+esc(q.page):"")'
        '+(q.name?" · "+esc(q.name):"")+(q.handles?" · "+esc(q.handles):"")'
        '+(q.credit?" · OK to credit":"")+(q.email?" · email "+esc(q.email):"")'
        '+"</p><p>"+esc(q.question)+"</p></article>"'
        '}).join("")||"<p class=\'empty\'>Nothing yet.</p>"})'
        '.catch(function(){b.disabled=false;n.textContent="That did not work."})})})();</script>'
    )
    page = page_shell("Questions", "Reader questions, behind a passphrase.", body, "/inbox/")
    page = page.replace("<head>", '<head><meta name="robots" content="noindex,nofollow">', 1)
    return {"/inbox/index.html": page}


def build_posters(content):
    """The page of cover stills.

    Posting an animated card as a video leaves the platform to choose a frame,
    and these cards open nearly empty. scripts/make_posters.py renders the
    settled frame of each card at 1080x1350; this lists them for download. It
    is RN's own tool, so it is written to posters/index.html on this machine
    and never into dist/: the stills are not served by the public site.
    """
    stills = sorted(p for p in (ROOT / "posters").glob("*.jpg"))
    if not stills:
        return {}
    rows = ['<div class="cards posters">']
    for s in stills:
        c = content.get(s.stem, {})
        title = c.get("title") or s.stem
        rows.append(
            f'<a href="{esc(s.name)}" download><img src="{esc(s.name)}" '
            f'alt="Cover still for {esc(title)}" loading="lazy" width="1080" height="1350">'
            f'<b>{esc(title)}</b><span>1080 × 1350</span></a>'
        )
    rows.append("</div>")
    body = (
        '<div class="index-head"><h1>Cover stills</h1>'
        f'<p>One still per card, {len(stills)} in all, at 1080 by 1350. Upload the still as the custom '
        'thumbnail when the card goes out as a video, so the cover is the finished frame rather than '
        'whatever the platform picks.</p></div>' + "".join(rows)
    )
    page = page_shell("Cover stills", "One 1080 by 1350 still per card, for use as a video thumbnail.", body, "/posters/")
    page = page.replace("<head>", '<head><meta name="robots" content="noindex,nofollow">', 1)
    return page


def safety_problems(pages, content):
    """What is wrong with the safety text on the pages about to be written.

    pages: {"/x/index.html": html} for every page the build writes.
    content: the built pieces, by slug.
    Every page must carry the standard block exactly once, in the footer, with
    its wording; it must link the warning key exactly when that page is built;
    and a piece with a hazard warning must show it once, after the title and
    before the first paragraph of the text."""
    out = []
    key_live = KEY_PATH in LIVE_PAGES
    for path, page in sorted(pages.items()):
        if not path.endswith("/index.html"):
            continue
        n = page.count('<aside class="safety"')
        if n != 1:
            out.append(f"{path}: standard safety block appears {n} times, not once")
            continue
        block = page[page.index('<aside class="safety"'):]
        block = block[:block.index("</aside>")]
        if page.rfind("<footer", 0, page.index('<aside class="safety"')) < 0 or "</footer>" not in page.split("</aside>", 1)[1]:
            out.append(f"{path}: safety block is not in the page footer")
        for need in (SAFETY_PHRASE, "call 911", POISON_HELP):
            if need not in block:
                out.append(f"{path}: safety block lacks {need!r}")
        has_key = f'href="{KEY_PATH}"' in block
        if key_live and not has_key:
            out.append(f"{path}: safety block does not link the warning key")
        if has_key and not key_live:
            out.append(f"{path}: safety block links the warning key, which is not built")
    for slug, c in sorted(content.items()):
        path = f"/{path_for(slug)}/index.html"
        page = pages.get(path)
        # Only piece pages: a piece whose address an index page also uses is not one.
        if page is None or not c.get("warning") or '<main class="reader" id="read">' not in page:
            continue
        if page.count('<div class="warn"') != 1:
            out.append(f"{path}: hazard warning is not shown exactly once")
            continue
        at = page.index('<div class="warn"')
        if esc(c["warning"]) not in page[at:page.index("</div>", at)]:
            out.append(f"{path}: hazard warning text is not the piece's own")
        body = c.get("body") or []
        first = page.find(f"<p>{esc(body[0])}</p>") if body else -1
        if page.find("</h1>") > at or (first >= 0 and at > first):
            out.append(f"{path}: hazard warning is not above the body text")
    return out


def main():
    check = "--check" in sys.argv
    every = load_content()
    releases = load_releases()
    today = today_hst()
    problems = []
    unrecorded = sorted(set(every) - set(releases))
    if unrecorded:
        problems.append(f"no entry in data/releases.json (held): {', '.join(unrecorded)}")
    content = {s: c for s, c in every.items() if is_released(releases.get(s), today)}
    for s in sorted(content):
        why = unfinished(s, content[s])
        if why:
            problems.append(f"{s} is dated for release but {why}: not built")
            del content[s]
    order = released_order(content, releases)
    LIVE_INDEXES.clear()
    LIVE_PAGES.clear()
    if any(f"/{path_for(s)}/" == KEY_PATH for s in content):
        LIVE_PAGES.add(KEY_PATH)
    kinds = {c.get("kind", "series") for c in content.values()}
    LIVE_INDEXES.update(p for p, ks, _, _ in INDEXES if kinds & set(ks))
    if any(c.get("original") for c in content.values()):
        LIVE_INDEXES.add("/archive/")
    # posters.html is an internal page of poster stills for RN's own posting,
    # not a reader card, so it is not built into the public site.
    cards = {p.stem for p in CARDS.glob("*.html")} - {"_home", "posters"}
    missing = sorted(cards - set(every))
    extra = sorted(set(every) - cards)
    if missing:
        problems.append(f"{len(missing)} cards have no content: {', '.join(missing[:8])}{' …' if len(missing) > 8 else ''}")
    if extra:
        problems.append(f"content with no card: {', '.join(extra)}")

    built = {}
    for slug, c in content.items():
        c.setdefault("slug", slug)
        page, note = build_card(slug, c, content, releases, order, today)
        if note:
            problems.append(note)
        if page:
            built[f"/{path_for(slug)}/index.html"] = page
    built.update(build_indexes(content))
    built.update(build_inbox())
    unsafe = safety_problems(built, content)

    search = [
        {"s": path_for(s), "t": c["title"], "d": c.get("dek", ""), "g": " ".join(c.get("tags", []))}
        for s, c in sorted(content.items())
    ]
    built["/search.json"] = json.dumps(search, ensure_ascii=False)
    indexes = [p for p, _, _, _ in INDEXES if p in LIVE_INDEXES] + (["/archive/"] if "/archive/" in LIVE_INDEXES else [])
    urls = ["/"] + [f"/{path_for(s)}/" for s in sorted(content)] + indexes + ["/ask/"]
    built["/sitemap.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{BASE}{u}</loc></url>\n" for u in urls)
        + "</urlset>\n"
    )
    built["/robots.txt"] = f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n"
    # The cards were first published at /aan-<slug>/; those links stay alive.
    built["/vercel.json"] = json.dumps(
        {"redirects": [
            {"source": f"/{s}", "destination": f"/{path_for(s)}", "permanent": True}
            for s in sorted(content) if path_for(s) != s
        ], "cleanUrls": True},
        indent=1,
    )

    print(f"today {today} (Pacific/Honolulu) · cards {len(cards)} · content {len(every)} · "
          f"released {len(content)} · held {len(every) - len(content)} · pages {len(built)}")
    for p in problems:
        print("  PROBLEM:", p)
    # A page without the standard safety text is never written, check or not.
    for p in unsafe:
        print("  SAFETY:", p)
    if unsafe:
        return 1
    if check:
        return 1 if problems else 0

    # Start from an empty dist/ so nothing held survives from an earlier build.
    if DIST.exists():
        shutil.rmtree(DIST)
    for rel, text in built.items():
        out = DIST / rel.lstrip("/")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    for extra_file in (ROOT / "assets").glob("*"):
        (DIST / extra_file.name).write_bytes(extra_file.read_bytes())
    # The cover stills stay on this machine. Only RN uses them.
    posters_page = build_posters(every)
    if posters_page:
        (ROOT / "posters" / "index.html").write_text(posters_page)
    # Link previews: the shared one, and one per released piece only.
    keep = {"_site"} | set(content)
    previews = sorted(p for p in (ROOT / "og").glob("*.png") if p.stem in keep)
    if previews:
        (DIST / "og").mkdir(parents=True, exist_ok=True)
        for preview in previews:
            (DIST / "og" / preview.name).write_bytes(preview.read_bytes())
    print(f"wrote {len(built)} files to {DIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
