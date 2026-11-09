"""A Fetch API scraper on Bright Data's Scraper API: any web page as Markdown."""

from .scrape import (
    FETCH_API,
    ApiError,
    Outcome,
    TokenMissing,
    fetch_one,
    fetch_snapshot,
    markdown,
    pages,
    run,
    scrape,
    status,
    token,
    trigger,
    write,
)

__all__ = [
    "FETCH_API",
    "ApiError",
    "Outcome",
    "TokenMissing",
    "fetch_one",
    "fetch_snapshot",
    "markdown",
    "pages",
    "run",
    "scrape",
    "status",
    "token",
    "trigger",
    "write",
]
__version__ = "0.1.0"
