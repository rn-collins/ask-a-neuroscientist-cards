#!/usr/bin/env python3
"""Render a 1080x1350 poster still for every card.

The cards are animations. Posting one as a video leaves the platform to pick a
cover frame, and the first frame of these cards is nearly empty, so each card
needs a still of its settled state to upload as the custom thumbnail.

Every card animates on its own schedule, so rather than guess one moment, this
captures each card at several points in its loop and keeps the fullest frame,
measured as the share of pixels that differ from the card's own background.

    python3 scripts/make_posters.py            # all cards
    python3 scripts/make_posters.py aan-awa    # just these

Chrome is driven headless at the card's exact size (the 540x675 stage scales
2x into 1080x1350). It does not exit on its own after writing a screenshot, so
each process is terminated by its own handle, never by name.
"""
import functools
import http.server
import pathlib
import shutil
import socketserver
import subprocess
import sys
import threading
import time

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
OUT = ROOT / "posters"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 8731
WIDTH, HEIGHT = 1080, 1350
MOMENTS = (3200, 4600, 6000)  # ms into the loop
PARALLEL = 5


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def ink(path):
    """Share of pixels that are not the background, as a rough fullness score."""
    im = Image.open(path).convert("RGB")
    bg = im.getpixel((4, 4))
    small = im.resize((270, 338))
    px = list(small.getdata())
    return sum(1 for p in px if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 24) / len(px)


def shoot(slug, ms, tmp):
    out = tmp / f"{slug}-{ms}.png"
    proc = subprocess.Popen(
        [
            CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", f"--window-size={WIDTH},{HEIGHT}",
            f"--virtual-time-budget={ms}", f"--user-data-dir={tmp}/profile-{slug}-{ms}",
            f"--screenshot={out}", f"http://127.0.0.1:{PORT}/cards/{slug}.html",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(600):  # up to 60s
        if out.exists() and out.stat().st_size > 0:
            time.sleep(0.35)  # let the write finish
            break
        time.sleep(0.1)
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    return out if out.exists() else None


def best(slug, tmp):
    shots = [s for s in (shoot(slug, ms, tmp) for ms in MOMENTS) if s]
    if not shots:
        return None, 0
    scored = sorted(((ink(s), s) for s in shots), reverse=True)
    return scored[0][1], scored[0][0]


def main():
    wanted = sys.argv[1:]
    slugs = sorted(p.stem for p in CARDS.glob("*.html") if p.stem not in {"_home", "posters"})
    if wanted:
        slugs = [s for s in slugs if s in wanted]
    OUT.mkdir(exist_ok=True)
    tmp = ROOT / ".posters-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    httpd = serve()
    done, thin = 0, []
    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(PARALLEL) as ex:
            for slug, (path, score) in zip(slugs, ex.map(lambda s: best(s, tmp), slugs)):
                if not path:
                    thin.append((slug, "no capture"))
                    continue
                im = Image.open(path).convert("RGB")
                if im.size != (WIDTH, HEIGHT):
                    im = im.resize((WIDTH, HEIGHT))
                im.save(OUT / f"{slug}.jpg", quality=92, optimize=True)
                done += 1
                if score < 0.04:
                    thin.append((slug, f"only {score:.1%} of the frame is inked"))
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {done} posters to {OUT}")
    for slug, why in thin:
        print(f"  CHECK {slug}: {why}")


if __name__ == "__main__":
    main()
