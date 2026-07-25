#!/usr/bin/env python3
"""Redact credentials / personal contact details from the style corpus.

Why: the Notion exports carried a boilerplate footer holding real TVBS
corporate logins (歐新社 / TVBS digital accounts) plus, in a few drafts, an
interviewee's phone extension. These were committed to the repo along with
the corpus. This script strips the VALUES while keeping the labels, so the
redaction stays auditable and the surrounding script text is untouched.

Scope (all corpus artifacts):
    raw/ , cleaned/ , sample_B*/ , draft_corpus.jsonl

What is redacted — only "label + value" lines, e.g.
    帳號 someaccount          →  帳號 [已移除]
    密碼 SomePass123           →  密碼 [已移除]
    分機 1234                 →  分機 [已移除]
Prose that merely mentions 帳號/密碼/分機 inside a sentence is NOT touched
(guarded by the anchored pattern + length limit + CJK check on the value).

Usage:
    python redact_secrets.py --dry-run     # report only
    python redact_secrets.py               # apply
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
JSONL = HERE / "draft_corpus.jsonl"
DIRS = ["raw", "cleaned", "sample_B", "sample_B2", "sample_B3", "sample_B4"]

PLACEHOLDER = "[已移除]"
CJK_RE = re.compile(r"[一-鿿]")

# Stage 2 — the same footer also embeds the login inside markdown links, e.g.
#   [https://epaimages.com/](...)[user@tvbs.com.tw](mailto:user@tvbs.com.tw)
# and sometimes drops the bare account token on its own line, so the anchored
# label rule alone cannot reach them. The agency URLs themselves are public
# and stay; only the corporate address and the account tokens go.
#
# The literal account tokens are NOT stored here — writing them into a tracked
# file would put the very secrets we are removing back into the repository.
# Put them one-per-line in `.secret-tokens.txt` (gitignored) when an exact-token
# sweep is needed; the structural rules below work without it.
CORP_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@tvbs\.com\.tw", re.I)
TOKENS_FILE = HERE / ".secret-tokens.txt"


def load_secret_tokens() -> list[str]:
    if not TOKENS_FILE.exists():
        return []
    return [t.strip() for t in TOKENS_FILE.read_text(encoding="utf-8").splitlines() if t.strip()]


SECRET_TOKENS = load_secret_tokens()

# Anchored: line STARTS with the label, then whitespace, then the value.
# Value must be short and contain no CJK — real credentials/extensions look
# like `someaccount`, `SomePass123`, `[a@b.com](mailto:a@b.com)`, `1234`.
LABEL_RE = re.compile(r"^(?P<label>帳號|密碼|分機)(?P<sep>[\s　]+)(?P<value>\S.*)$")
MAX_VALUE_LEN = 80


def redact_line(line: str) -> str | None:
    """Return redacted line, or None if the line should stay as-is."""
    stripped = line.strip()
    m = LABEL_RE.match(stripped)
    if not m:
        return None
    value = m.group("value").strip()
    if len(value) > MAX_VALUE_LEN or CJK_RE.search(value):
        return None          # prose, not a credential record
    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}{m.group('label')} {PLACEHOLDER}"


def redact_text(text: str) -> tuple[str, int]:
    out, n = [], 0
    for line in text.splitlines():
        new = redact_line(line) or line          # stage 1: label + value lines
        new = CORP_EMAIL_RE.sub(PLACEHOLDER, new)  # stage 2: embedded secrets
        for tok in SECRET_TOKENS:
            new = new.replace(tok, PLACEHOLDER)
        if new != line:
            n += 1
        out.append(new)
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + trailing, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total_files = total_lines = 0

    for d in DIRS:
        base = HERE / d
        if not base.exists():
            continue
        files = hits = 0
        for f in base.rglob("*.md"):
            text = f.read_text(encoding="utf-8", errors="replace")
            new, n = redact_text(text)
            if n:
                files += 1
                hits += n
                if not args.dry_run:
                    f.write_text(new, encoding="utf-8")
        print(f"{d + '/':14s} {files:4d} files, {hits:5d} lines redacted")
        total_files += files
        total_lines += hits

    # JSONL: redact inside the stored draft/note fields
    recs = [json.loads(l) for l in JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    jf = jl = 0
    for r in recs:
        changed = 0
        for field in ("draft", "note"):
            if r.get(field):
                new, n = redact_text(r[field])
                if n:
                    r[field] = new
                    changed += n
        if changed:
            jf += 1
            jl += changed
    if not args.dry_run and jf:
        with JSONL.open("w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{'draft_corpus':14s} {jf:4d} records, {jl:5d} lines redacted")

    mode = "DRY RUN — nothing written" if args.dry_run else "APPLIED"
    print(f"\n{mode}. total {total_files + jf} artifacts, {total_lines + jl} lines.")


if __name__ == "__main__":
    main()
