"""Rewrite the README's field tables from the published scraper schemas.

    python .github/scripts/field_tables.py

No token needed: this reads
https://docs.brightdata.com/scrapers-full.json, the list the Bright Data MCP
server also loads: every scraper's output fields, with type and description.
"""

import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
START, END = "<!-- fields:start -->", "<!-- fields:end -->"
SOURCE = "https://docs.brightdata.com/scrapers-full.json"

#: The README's order. Each scraper's collect_by_url method lists its full record.
SCRAPERS = [
    ("gd_m6gjtfmeh43we6cqc", "page"),
]


def table(fields):
    rows = ["| field | type | description |", "| --- | --- | --- |"]
    for field in fields:
        desc = (field.get("description") or "").replace(" — ", ": ").replace("—", ":")
        # no fences, no table breaks
        desc = " ".join(desc.split()).replace("`", "'").replace("|", "/")
        rows.append(f"| `{field['name']}` | {field.get('type', '')} | {desc} |")
    return rows


def main():
    text = README.read_text(encoding="utf-8")
    assert START in text and END in text, "README field-table markers are missing"
    with urllib.request.urlopen(SOURCE, timeout=120) as response:
        published = {s["id"]: s for s in json.load(response)}
    sample = json.loads((ROOT / "examples" / "sample_output.json").read_text(encoding="utf-8"))
    first = sample["pages"][0]["page"]
    lines = [
        START,
        "Regenerated every day from the published schema,",
        f"[scrapers-full.json]({SOURCE}), so they cannot go stale. A record",
        "carries the fields that apply to it, plus `timestamp` and `input`; the",
        f"sample file's first page has {len(first)} keys.",
    ]
    counts = []
    for dataset, label in SCRAPERS:
        fields = published[dataset]["scrapers"]["collect_by_url"]["output_fields"]
        counts.append(len(fields))
        lines += [
            "",
            "<details>",
            f"<summary>All {len(fields)} {label} fields, <code>{dataset}</code></summary>",
            "",
            *table(fields),
            "",
            "</details>",
        ]
    lines.append(END)
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: "\n".join(lines), text,
                 flags=re.S)
    README.write_text(new, encoding="utf-8")
    state = "updated" if new != text else "already current"
    print(f"\nSchemas: {len(SCRAPERS)} scrapers, {sum(counts)} fields. Tables {state}.")


if __name__ == "__main__":
    main()
