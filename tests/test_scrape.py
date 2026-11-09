"""These run without a token. The API is a stub."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

import fetch_api_scraper.__main__ as cli

# the package exports a function named scrape, which hides the module of that name
fa = sys.modules["fetch_api_scraper.scrape"]

ROOT = Path(__file__).resolve().parents[1]
PAGE = {"page_title": "Example Domain", "markdown": "# Example Domain\n", "url": "https://example.com"}


class FakeApi:
    """Answers trigger, progress and snapshot the way the live API does."""

    def __init__(self, rows=None, states=("ready",)):
        self.rows = rows or []
        self.states = list(states)
        self.calls = []

    def __call__(self, path, body=None):
        self.calls.append((path, body))
        if path.startswith("/trigger"):
            return {"snapshot_id": "sd_test"}
        if path.startswith("/progress/"):
            return {"status": self.states.pop(0) if len(self.states) > 1 else self.states[0]}
        if path.startswith("/snapshot/"):
            return self.rows
        raise AssertionError(path)

    def trigger(self):
        path, body = self.calls[0]
        return dict(urllib.parse.parse_qsl(path.split("?", 1)[1])), body


@pytest.fixture
def api(monkeypatch):
    def install(**kwargs):
        fake = FakeApi(**kwargs)
        monkeypatch.setattr(fa, "_call", fake)
        monkeypatch.setattr(fa, "POLL_SECONDS", 0)
        return fake

    return install


@pytest.fixture
def no_login(monkeypatch, tmp_path):
    """No token in the environment and no CLI login: the stranger's machine."""
    monkeypatch.delenv("BRIGHTDATA_API_TOKEN", raising=False)
    monkeypatch.setattr(fa, "_cli_credentials", lambda: tmp_path / "missing.json")


def test_urls_go_in_one_job_and_the_country_is_upper_case(api):
    fake = api()
    fa.pages(["https://example.com", "https://example.org"], "de")

    query, body = fake.trigger()
    assert query == {"dataset_id": fa.FETCH_API, "include_errors": "true"}
    assert body == [
        {"url": "https://example.com", "country": "DE"},
        {"url": "https://example.org", "country": "DE"},
    ]


def test_no_country_sends_no_country(api):
    fake = api()
    fa.pages("https://example.com")
    assert fake.trigger()[1] == [{"url": "https://example.com"}]


def test_markdown_returns_the_page_or_raises_the_error_row(api):
    api(rows=[PAGE])
    assert fa.markdown("https://example.com") == "# Example Domain\n"

    api(rows=[{"error": "The navigation resulted in a dead page (404 status code)"}])
    with pytest.raises(fa.ApiError, match="dead page"):
        fa.markdown("https://example.com/missing")


def test_run_polls_until_the_snapshot_is_ready(api):
    fake = api(rows=[PAGE], states=("running", "running", "ready"))
    assert fa.run(fa.FETCH_API, [{"url": "x"}]) == [PAGE]
    assert [p for p, _ in fake.calls].count("/progress/sd_test") == 3


def test_a_dropped_poll_does_not_lose_the_job(api, monkeypatch):
    fake = api(rows=[PAGE])
    dropped = []

    def flaky(path, body=None):
        if path.startswith("/progress/") and not dropped:
            dropped.append(path)
            raise urllib.error.URLError("connection reset")
        return fake(path, body)

    monkeypatch.setattr(fa, "_call", flaky)
    assert fa.run(fa.FETCH_API, [{"url": "x"}]) == [PAGE]
    assert dropped


def test_a_failed_snapshot_is_an_error(api):
    api(states=("failed",))
    with pytest.raises(fa.ApiError, match="sd_test failed"):
        fa.run(fa.FETCH_API, [{"url": "x"}])


def test_a_job_that_never_finishes_times_out(api):
    api(states=("running",))
    with pytest.raises(TimeoutError, match="timeout"):
        fa.run(fa.FETCH_API, [{"url": "x"}], timeout=0)


def test_an_http_error_names_the_status_and_the_reason(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_TOKEN", "test")

    def refuse(request, timeout):
        body = io.BytesIO(b'{"errors":[["url","This value should be a valid URL"]]}')
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, body)

    monkeypatch.setattr(fa.urllib.request, "urlopen", refuse)
    with pytest.raises(fa.ApiError, match="HTTP 400.*url"):
        fa.trigger(fa.FETCH_API, [{"url": "not a url"}])


def test_the_token_comes_from_the_environment_then_the_cli_login(monkeypatch, tmp_path, no_login):
    with pytest.raises(fa.TokenMissing, match="export BRIGHTDATA_API_TOKEN"):
        fa.token()

    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"api_key": "from-login"}), encoding="utf-8")
    monkeypatch.setattr(fa, "_cli_credentials", lambda: credentials)
    assert fa.token() == "from-login"

    monkeypatch.setenv("BRIGHTDATA_API_TOKEN", "from-env")
    assert fa.token() == "from-env"


def test_a_page_reports_its_title_and_markdown_size(api):
    api(rows=[{**PAGE, "markdown": "x" * 9308}])
    outcome = fa.fetch_one("https://example.com")

    assert outcome.ok
    assert outcome.line() == "got     https://example.com: 'Example Domain', 9,308 characters of Markdown"


def test_an_error_row_fails_the_url(api):
    api(rows=[{"error": "The navigation resulted in a dead page (404 status code)", "error_code": "dead_page"}])
    outcome = fa.fetch_one("https://example.com/missing")

    assert not outcome.ok
    assert outcome.line() == (
        "failed  https://example.com/missing: The navigation resulted in a dead page (404 status code)"
    )


def test_one_bad_url_does_not_end_the_run(monkeypatch):
    def pages(url, country=None):
        if url == "boom":
            raise RuntimeError("boom")
        return [{"page_title": url}]

    monkeypatch.setattr(fa, "pages", pages)
    first, second = fa.scrape(["boom", "https://example.com"])

    assert first.error == "RuntimeError: boom"
    assert second.ok and second.page == {"page_title": "https://example.com"}


def test_a_run_writes_what_it_found(api, tmp_path):
    api(rows=[PAGE])
    path = fa.write(fa.scrape(["https://example.com"]), tmp_path / "out.json")

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["pages"] == [{"url": "https://example.com", "page": PAGE}]
    assert document["generated_at"]


def fake_cli(monkeypatch, outcome_for, seen=None):
    monkeypatch.setattr(cli, "token", lambda: "test")

    def fetch_one(url, country):
        if seen is not None:
            seen.append((url, country))
        return outcome_for(url)

    monkeypatch.setattr(cli, "fetch_one", fetch_one)


def test_the_cli_exit_code_says_whether_every_url_worked(monkeypatch, tmp_path):
    fake_cli(monkeypatch, lambda u: fa.Outcome(u, page=PAGE))
    assert cli.main(["https://example.com", "--out", str(tmp_path / "ok.json")]) == 0

    fake_cli(monkeypatch, lambda u: fa.Outcome(u, error="boom"))
    assert cli.main(["https://example.com", "--out", str(tmp_path / "bad.json")]) == 1


def test_the_cli_passes_the_country_upper_case_and_none_by_default(monkeypatch, tmp_path):
    seen = []
    fake_cli(monkeypatch, lambda u: fa.Outcome(u, page=PAGE), seen)
    cli.main(["https://example.com", "--country", "de", "--out", str(tmp_path / "o.json")])
    cli.main(["https://example.com", "--out", str(tmp_path / "o.json")])
    assert seen == [("https://example.com", "DE"), ("https://example.com", None)]


def test_each_result_prints_before_the_next_url_starts(monkeypatch, tmp_path, capsys):
    fake_cli(monkeypatch, lambda u: fa.Outcome(u, page=PAGE))
    cli.main(["https://example.com", "https://example.org", "--out", str(tmp_path / "o.json")])

    out = capsys.readouterr().out.splitlines()
    assert [ln for ln in out if ln.startswith(("asking", "got"))] == [
        "asking  https://example.com...",
        "got     https://example.com: 'Example Domain', 17 characters of Markdown",
        "asking  https://example.org...",
        "got     https://example.org: 'Example Domain', 17 characters of Markdown",
    ]


def test_a_bad_country_is_refused_before_any_request(capsys):
    with pytest.raises(SystemExit):
        cli.main(["https://example.com", "--country", "USA"])
    assert "two-letter country code" in capsys.readouterr().err


def test_a_missing_token_is_a_message_not_a_traceback(no_login, capsys):
    assert cli.main(["https://example.com"]) == 2
    err = capsys.readouterr().err
    assert "export BRIGHTDATA_API_TOKEN" in err and "bdata login" in err
    assert "Traceback" not in err


def test_piped_output_keeps_the_header_before_the_error(tmp_path):
    """A log or an agent reads a pipe. The header must not land after the error."""
    env = {k: v for k, v in os.environ.items() if k != "BRIGHTDATA_API_TOKEN"}
    env["HOME"] = str(tmp_path)  # no CLI login: the stranger's machine
    env["APPDATA"] = str(tmp_path)
    run = subprocess.run(
        [sys.executable, "-m", "fetch_api_scraper", "https://example.com"],
        cwd=tmp_path,
        env={**env, "PYTHONPATH": str(ROOT / "src")},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=60,
    )
    assert run.returncode == 2, run.stdout
    assert run.stdout.index("Fetching 1 page(s)") < run.stdout.index("API token required")


def test_the_readme_excerpt_is_the_start_of_the_example_file():
    """The README shows the first 20 lines of the real file, verbatim, and links it."""
    sample = (ROOT / "examples" / "sample_output.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "\n".join(sample.splitlines()[:20]) in readme, "README excerpt drifted from the file"
    assert "](examples/sample_output.json)" in readme


def test_every_in_page_link_has_its_heading():
    """A renamed heading would break the header row silently; the link check sees only URLs."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    headings = re.findall(r"^#{1,6} (.+)$", readme, re.M)
    anchors = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in headings}
    for anchor in re.findall(r"\]\(#([^)]+)\)", readme):
        assert anchor in anchors, f"#{anchor} points at no heading"
