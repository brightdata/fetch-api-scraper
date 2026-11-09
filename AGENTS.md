# For coding agents working in this repository

Read this before changing anything. Every line below was verified against the
live API or the Bright Data CLI 0.4.1 on 2026-11-09. Where the API reference
pages disagree with the live API, the live API is what is written here.

## Auth

- `token()` reads `BRIGHTDATA_API_TOKEN`, then the key `bdata login` stored in
  `brightdata-cli/credentials.json` (the same file the Python SDK reads).
  Setting the variable, or running the login once, is the one step a human
  must do; never paste a key into code.
- The raw HTTP Quickstart in the README reads `BRIGHTDATA_API_TOKEN` only. It
  does not see the CLI login.

## How the API behaves

- One dataset, `gd_m6gjtfmeh43we6cqc`, collect by URL only. Inputs: `url`,
  optional `country`.
- The product name is Fetch API. Do not write "Crawl API", and do not use the
  Python SDK's `client.crawler.crawl`: Bright Data's docs avoid both.
- This package calls `https://api.brightdata.com/datasets/v3` with the
  standard library and has no dependencies. The snapshot download is
  `fetch_snapshot`, not `fetch`, so it is never confused with the product.
- Every call is an asynchronous job: `/trigger`, poll `/progress/<id>`, then
  `/snapshot/<id>?format=json`. A page took 7 to 44 seconds; an unknown host
  took 147 to fail. `TIMEOUT` is 900.
- A status poll that fails with a network error is retried until the
  deadline. An HTTP error still raises.
- Always send `include_errors=true`. A 404 is an error row, `dead_page`; an
  unresolvable host is an error row, error_code `proxy`.
- Live behaviour on 2026-11-09:
  - Each record: `markdown`, `html2text`, `page_html`, `page_title`, `url`,
    `final_url`, `country`, and `ld_json` only when the page has any.
  - `ld_json` is a JSON string; on Wikipedia it parses to a list.
  - `markdown` is the whole page, navigation included.
  - `country`: send it upper case. Left out, the record's `country` is null.
    Checked against https://ipinfo.io/country, 8 of 10 requests came from the
    country asked for and 2 (JP once, FR once) came from Spain, while the
    record's `country` still echoed the input. It is not proof of the exit
    country.
  - A bot-protected Zillow search page came back in 12 seconds.
- The schema changes without notice. Never hardcode a field list.
- The full documentation index, one `.md` page per entry:
  https://docs.brightdata.com/llms.txt

## Working here

- `pytest` runs offline and needs no token. `ruff check .` must pass.
- CI follows the README's own commands on an empty machine, finding its
  sections by their exact H2 text. Rename a heading in ci.yml too.
- A weekly workflow executes every fenced block in the README against the real
  API, and a daily one runs a smaller live check. A snippet must be complete
  and paste-able on its own, and its shown output must be real.
- The field table in the README sits between `<!-- fields:start -->` and
  `<!-- fields:end -->` and is regenerated daily by
  `.github/scripts/field_tables.py` from
  https://docs.brightdata.com/scrapers-full.json. Do not edit it by hand.
- The "last verified" badge line at the top of the README is rewritten by the
  daily run. Do not edit it by hand.
- Headings are written for search: "Fetch API scraper for Python", "How to scrape ...". Keep that
  pattern when adding a section.
- Keep it small. Beyond the status poll, do not add retries, deduplication,
  scheduling, databases, async examples or concurrency.
