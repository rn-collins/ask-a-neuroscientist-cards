# Ask a Neuroscientist: the series companion site (open edition)

The companion site for RN Collins's series on how plants, places and daily life act on the brain. The series began at *Fat Nugs Magazine*. Each piece is an animated post card with a written explanation under it: the mechanism, a warning where one applies, the sources, and where to go next.

**Live site:** https://rn-ask-a-neuroscientist.vercel.app
**Author:** [RN Collins](https://rn-selected-work.vercel.app)

Education, not medical or legal advice.

## What this repository is

This is the open edition. It holds everything needed to rebuild the live site: the build, the tests, the stylesheet, and the cards and written content of the pieces that have been released. As of 2026-10-13 that is 1 of the 113 pieces in the series.

The other 112 pieces are not here. The series is released on a calendar, and a public repository would publish every unreleased card, text and source list ahead of that calendar. They live in a private source repository, which is where the site is built and deployed from. Here they appear only as one number in `data/withheld.json`: no title, no date, no text, no source.

The site you build from this repository for a given date is byte-identical to the live site built from the private source repository for the same date. A script in the private source repository writes this edition and refuses to finish if any withheld piece's identifier, title or text turns up in the output.

This repository is regenerated whenever a piece is released, so its history is a series of release snapshots.

### What is left out, and why

| Left out | Why |
|---|---|
| Unreleased cards and content | They follow a release calendar. |
| `api/` (`/api/question`, `/api/inbox`) | The reader-question form and the inbox store what strangers type, which can include names, social handles and health details. The handlers have no rate limit and the inbox sits behind a single shared passphrase. They stay in the private repository until they are hardened. |
| The daily deploy workflow | It deploys to a private Vercel project with repository secrets. |
| Authoring and process files | Internal working notes and commit rules for the maintainers. |
| `scripts/archive_cards.py`, `scripts/questions.py` | The first regenerates cards from a held template. The second reads the question store behind `api/`. |

Because `api/` is not included, the question form that the build puts on every page posts to a path that does not exist if you deploy this repository as it is. To run your own copy, either supply a handler at `/api/question` or remove the form (`ask_block` in `scripts/build.py`).

## How a piece becomes public

`data/releases.json` is the only gate. A piece is built when its `hold` is `false` and its `releasedAt` date is today or earlier in Pacific/Honolulu. Every other piece is left out of everything the build writes: its page, the index pages, the search index, the sitemap, the redirects and its link preview, so its address returns 404. A piece marked `"role": "template"`, or whose card or content still carries placeholder text, is never built, whatever its release record says.

| Field | Meaning |
|---|---|
| `id` | A shared id such as `fatnugs/fn-01`. |
| `slug` | The file name stem of the card and the content file. `arc-coa` is published at `/coa/`; the stored path redirects. |
| `releasedAt` | Release date in Pacific/Honolulu, `YYYY-MM-DD`. Empty means unreleased. |
| `hold` | `true` keeps the piece hidden whatever its date. |
| `postUrls` | Links to posts about the piece. |
| `longFormUrl` | The full article the piece belongs with. |
| `sourcePageUrl` | The sources page for the piece. |
| `otherSourcePages` | Further sources pages, each shown once its own `releasedAt` has come. |

## Build and test

Python 3.9 or newer, standard library only. No dependencies, except Pillow for the optional link-preview images.

```sh
python3 scripts/build.py                      # writes dist/ for today in Honolulu
python3 scripts/build.py --today 2026-10-18   # builds as if it were that day
python3 scripts/build.py --check              # reports problems, writes nothing
python3 tests/test_release_gate.py            # release gate and output tests
python3 -m http.server 8000 --directory dist  # preview at http://localhost:8000/
```

Every page is written as `<path>/index.html`, so the folder address works on any static host. `dist/vercel.json` carries the redirects from the old `/aan-<slug>` and `/arc-<slug>` addresses and sets `cleanUrls` for Vercel.

Optional:

```sh
python3 -m pip install pillow
python3 scripts/og.py        # draws link previews into og/ (run build.py afterwards, it copies them into dist/og/)
python3 scripts/make_posters.py   # cover stills into posters/ (needs Google Chrome; the path is set for macOS)
```

`og/` and `posters/` are git-ignored: they are generated, and the build copies a preview into `dist/` only for a released piece.

The tests build the site for the day before the first release, the first release day and the last release day, into a temporary folder, and check that:

- the gate treats the boundaries correctly (today, tomorrow, empty date, `hold`);
- every row in `data/releases.json` has its card and content file;
- every built page is a released piece, and the sitemap, search index and redirects name released pieces only;
- every internal link on every built page (previous, next, related, index and kicker links) lands on a page that was built.

## Layout

| Path | What it is |
|---|---|
| `cards/` | The animated post cards, one HTML file each. They are the graphics recorded for social and the hero of their page. |
| `content/` | One JSON file per card: the text under it. |
| `data/releases.json` | The release record for every public piece. |
| `data/withheld.json` | How many pieces are withheld. Nothing else about them. |
| `assets/aan.css` | The reader layer. The cards keep their own styles. |
| `scripts/build.py` | Writes `dist/`: a page per released card, the index pages, the search index, the sitemap, robots and redirects. |
| `scripts/og.py` | Draws the 1200 by 630 link preview for each page. |
| `scripts/make_posters.py` | Renders a 1080 by 1350 still of each card, for use as a video thumbnail. |
| `tests/` | The release gate and output tests. |

### Content file schema

Each `content/<slug>.json` has:

| Key | Meaning |
|---|---|
| `slug`, `title`, `dek` | The card stem, the headline and the one-line summary. |
| `kind` | One of `plant`, `place`, `receptor`, `term`, `myth`, `daily-life`, `series`, `archive`. It decides which index lists the piece. |
| `body` | A list of paragraphs. |
| `warning` | The warning shown under the body. |
| `sources` | A list of `{title, publisher, date, url, supports}`; `supports` says what the source backs. |
| `related`, `tags` | Slugs to link next, and search tags. In this edition `related` lists released pieces only. |
| `original` | Optional. Where the piece first appeared: `{title, url, publication, date}`. |
| `card` | Optional. The text for a card drawn from an archive piece. |
| `role` | Optional. `template` is never built; `series-furniture` marks the series' own cover, opener and closing cards. |

## House rules for content

Every page states the mechanism and names its sources. Nothing is invented: no made-up examples, no hypothetical people, no unsourced claims. Warnings are written as warnings, legal status is stated as of the date on the page, and nothing here is medical or legal advice.

## Corrections

If you find an error in a piece, open an issue on this repository with the page address and the source that disagrees.

## License

The code (`scripts/`, `tests/`, `.github/`, `assets/aan.css`) is MIT: see [LICENSE](LICENSE). The text, cards and data (`content/`, `cards/`, `data/`) are copyright RN Collins, all rights reserved: see [LICENSE-CONTENT](LICENSE-CONTENT). You may quote short passages with credit and a link to the site.
