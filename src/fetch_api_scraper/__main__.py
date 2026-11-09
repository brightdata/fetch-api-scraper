"""fetch-api-scraper https://example.com, or python -m fetch_api_scraper https://example.com"""

from __future__ import annotations

import argparse
import re
import sys
import threading
import time
from contextlib import contextmanager

from .scrape import TokenMissing, fetch_one, token, write

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def country_code(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z]{2}", value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a two-letter country code, like US")
    return value.upper()


@contextmanager
def waiting(label: str):
    """A spinner and a running clock, so minutes of waiting look alive.

    Outside a terminal it prints one plain line instead: a log wants a line,
    not an animation.
    """
    if not sys.stdout.isatty():
        print(f"asking  {label}...", flush=True)
        yield
        return
    done = threading.Event()
    started = time.monotonic()

    def spin() -> None:
        frame = 0
        while not done.wait(0.1):
            secs = int(time.monotonic() - started)
            clock = f"{secs // 3600}:{secs // 60 % 60:02d}:{secs % 60:02d}"
            sys.stdout.write(f"\r\033[2K{FRAMES[frame % len(FRAMES)]} {label} {clock}")
            sys.stdout.flush()
            frame += 1

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join()
        sys.stdout.write("\r\033[2K")  # leave the line clean for the result
        sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fetch-api-scraper",
        description="Fetch one or more web pages as Markdown, text, HTML and JSON-LD.",
    )
    parser.add_argument("urls", nargs="+", help="public page URLs, such as https://example.com")
    parser.add_argument("--country", type=country_code, default=None,
                        help="two-letter country to request the pages from, such as US")
    parser.add_argument("--out", default="pages.json", help="output file, default %(default)s")
    args = parser.parse_args(argv)

    print(
        f"Fetching {len(args.urls)} page(s)"
        f"{f' from {args.country}' if args.country else ''}\n"
        "Usually under a minute each. Billed per page, 5,000 free credits a month.",
        flush=True,  # piped, an unflushed header would print after the error below
    )
    try:
        token()  # fail before the first wait, not after it
    except TokenMissing as exc:
        print(exc, file=sys.stderr)
        return 2

    outcomes = []
    for url in args.urls:
        with waiting(url):
            outcome = fetch_one(url, args.country)
        print(outcome.line(), flush=True)
        outcomes.append(outcome)

    path = write(outcomes, args.out)
    fetched = sum(1 for o in outcomes if o.ok)
    print(f"\nSaved {fetched} pages as JSON to {path}")
    return 0 if all(o.ok for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
