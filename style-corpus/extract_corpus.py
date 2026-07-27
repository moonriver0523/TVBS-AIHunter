#!/usr/bin/env python3
"""Clean the raw Notion export of Denis's Daily Draft corpus and pull out the
Draft section (his actual written narrative) as a style-reference corpus.

Source: style-corpus/raw/【Daily Draft】/*.md, copied verbatim from the
Denis-News-Knowledge-Base repo (00_Inbox/documents/【Daily Draft】/).

Each raw file mixes three things:
  - `¤WA<n> <len> <hex>` lines: MOS/VizRT clipboard metadata pasted into
    Notion by accident. Pure noise, not text content — stripped entirely.
  - `### *Materials*`: the source material list (wire scripts, TC notes).
    Not style-relevant — this is what he read, not what he wrote.
  - `### *Draft*`: his actual finished narrative script. This is the style
    target for CTV/SOT quality work.
  - `### ***Note***` (or `*Note*`): CG (Chyron) caption text draft — a
    separate, shorter style (headline/label register, not narrative prose).

Known limitation — one file can hold several unrelated stories (B7-M7)
--------------------------------------------------------------------
Measured at 12.5% of the B7 sample: a single Daily Draft file sometimes
contains two or three separate news items written the same day (e.g. the
Honduran election result *and* a southern-California storm). Nothing here
splits them, so every downstream consumer sees only the first/dominant one.
Consequences already observed:
  - topic distribution stats undercount the trailing stories
  - topic-coverage sampling wastes quota (you read the story that was not
    the one the quota was for)
  - techniques get attributed to the wrong topic

No reliable split signal found yet. The obvious candidate — a second
`網路標:` block — was measured against the 40-draft B7 sample and only
catches 1 of the 5 composite files (0 false positives, 4 missed): the
trailing stories usually share one headline block rather than opening a new
one. Do not build a splitter on that signal alone.

Usage:
    python extract_corpus.py
Writes:
    style-corpus/cleaned/<same filename>.md   — noise-stripped copy of each file
    style-corpus/draft_corpus.jsonl           — one JSON object per file with
                                                 {file, date, draft, note, headlines}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw" / "【Daily Draft】"
CLEANED_DIR = HERE / "cleaned"
OUT_JSONL = HERE / "draft_corpus.jsonl"

NOISE_LINE_RE = re.compile(r"^¤WA\d+\s+\d+\s+[0-9A-Fa-f]+\s*$")

# H3 headers seen across the corpus (spelling varies: `*Draft*`, `***Note***`, etc.)
SECTION_RE = re.compile(r"^###\s*(.+?)\s*$")

DRAFT_HEADERS = {"*draft*", "draft", "*final*"}
NOTE_HEADERS = {"***note***", "*note*", "note"}
MATERIALS_HEADERS = {"*materials*", "materials"}


def strip_noise(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not NOISE_LINE_RE.match(ln)]
    # collapse the runs of blank lines the stripped blobs leave behind
    cleaned: list[str] = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run > 2:
                continue
        else:
            blank_run = 0
        cleaned.append(ln)
    return "\n".join(cleaned).strip() + "\n"


def split_sections(text: str) -> dict[str, str]:
    """Split a cleaned file into {header_text_lower: body} by H3 headers."""
    sections: dict[str, str] = {}
    current_key: str | None = None
    buf: list[str] = []
    for ln in text.splitlines():
        m = SECTION_RE.match(ln)
        if m:
            if current_key is not None:
                sections[current_key] = "\n".join(buf).strip()
            current_key = m.group(1).strip().lower()
            buf = []
        else:
            buf.append(ln)
    if current_key is not None:
        sections[current_key] = "\n".join(buf).strip()
    return sections


def first_matching(sections: dict[str, str], wanted: set[str]) -> str | None:
    for key, body in sections.items():
        if key in wanted:
            return body
    return None


def guess_date(filename: str) -> str | None:
    m = re.match(r"^(\d{3,4})", filename)
    return m.group(1) if m else None


def main() -> None:
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW_DIR.rglob("*.md"))
    print(f"Found {len(files)} raw files under {RAW_DIR}")

    n_ok = 0
    n_no_draft = 0
    with OUT_JSONL.open("w", encoding="utf-8") as out:
        for f in files:
            rel = f.relative_to(RAW_DIR)
            raw = f.read_text(encoding="utf-8", errors="replace")
            cleaned = strip_noise(raw)
            cleaned_path = CLEANED_DIR / rel
            cleaned_path.parent.mkdir(parents=True, exist_ok=True)
            cleaned_path.write_text(cleaned, encoding="utf-8")

            sections = split_sections(cleaned)
            draft = first_matching(sections, DRAFT_HEADERS)
            note = first_matching(sections, NOTE_HEADERS)

            # blockquote placeholders (`> `) with nothing else mean the
            # section header exists but was never filled in — treat as empty.
            def is_empty(body: str | None) -> bool:
                if not body:
                    return True
                stripped = "\n".join(
                    ln for ln in body.splitlines() if ln.strip() not in ("", ">")
                ).strip()
                return stripped == ""

            if is_empty(draft):
                n_no_draft += 1
                continue

            record = {
                "file": str(rel).replace("\\", "/"),
                "date_prefix": guess_date(f.name),
                "draft": draft.strip(),
                "note": None if is_empty(note) else note.strip(),
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n_ok += 1

    print(f"Wrote {n_ok} records with non-empty Draft to {OUT_JSONL}")
    print(f"Skipped {n_no_draft} files with empty/missing Draft section")
    print(f"Cleaned copies written to {CLEANED_DIR}")


if __name__ == "__main__":
    main()
