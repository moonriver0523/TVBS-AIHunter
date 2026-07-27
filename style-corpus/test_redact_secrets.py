#!/usr/bin/env python3
"""Unit tests for redact_secrets.

Run:  python test_redact_secrets.py

These guard the two failure modes we have actually hit:
  1. Over-redaction — a news script that merely *mentions* 帳號／密碼／分機
     in prose must survive untouched. (This is why the label rule is anchored
     and guarded by a length limit and a CJK check on the value.)
  2. Under-redaction — the 2026-07-25 sweep left every bare, unlabelled
     credential token in place because only "label + value" lines were
     matched. Stage 3 exists to catch those; these tests pin it down.

No real credential appears in this file. The token list is monkeypatched with
obvious fakes, which is also why the module is re-configured rather than
imported cold.
"""

from __future__ import annotations

import re
import sys

import redact_secrets as R

FAKE_TOKENS = ["FakePass@@999", "Fake@999", "Fake@@longer999", "Z+9Qq1*wXyZ^A2b"]

# Re-wire the module to the fakes, mirroring how load_secret_tokens() feeds it.
R.SECRET_TOKENS = sorted(FAKE_TOKENS, key=len, reverse=True)
R.TOKEN_RE = re.compile("|".join(re.escape(t) for t in R.SECRET_TOKENS))

P = R.PLACEHOLDER
CASES: list[tuple[str, str, str]] = []


def case(name: str, src: str, want: str) -> None:
    CASES.append((name, src, want))


# --- stage 1: anchored label + value ---------------------------------------
case("label 帳號", "帳號 someaccount", f"帳號 {P}")
case("label 密碼", "密碼 SomePass123", f"密碼 {P}")
case("label 分機", "分機 1234", f"分機 {P}")
case("label keeps indent", "  密碼 SomePass123", f"  密碼 {P}")
case("label with markdown link value",
     "帳號 [a@b.com](mailto:a@b.com)", f"帳號 {P}")

# --- stage 1 guards: prose must survive ------------------------------------
case("prose mentioning 密碼 mid-sentence",
     "駭客竊取用戶的密碼與個資，受害者高達千人",
     "駭客竊取用戶的密碼與個資，受害者高達千人")
case("label followed by CJK value is prose",
     "密碼 外洩事件震驚全球",
     "密碼 外洩事件震驚全球")
case("over-long value is not a credential",
     "帳號 " + "x" * 100,
     "帳號 " + "x" * 100)
case("label with no value", "帳號", "帳號")

# --- stage 2: corporate mail embedded anywhere -----------------------------
case("corporate mail inline",
     "聯絡 someone@tvbs.com.tw 索取", f"聯絡 {P} 索取")
case("public agency URL survives",
     "[https://epaimages.com/](https://epaimages.com/)",
     "[https://epaimages.com/](https://epaimages.com/)")
case("external mail survives",
     "寄到 stranger@example.com 即可",
     "寄到 stranger@example.com 即可")

# --- stage 3: bare unlabelled tokens (the 2026-07-25 miss) -----------------
case("bare token on its own line", "FakePass@@999", P)
case("bare token among footer lines",
     "NEWSCOM\nZ+9Qq1*wXyZ^A2b\n標示寫 (圖／達志影像Newscom)",
     f"NEWSCOM\n{P}\n標示寫 (圖／達志影像Newscom)")
case("longer token wins over its prefix", "Fake@@longer999", P)
case("short token still matched when standalone", "Fake@999", P)

# --- multiline document integrity ------------------------------------------
case("mixed document",
     "歐新社帳密\n帳號 someaccount\n密碼 SomePass123\nFakePass@@999\n記者報導密碼外洩案",
     f"歐新社帳密\n帳號 {P}\n密碼 {P}\n{P}\n記者報導密碼外洩案")
case("trailing newline preserved", "帳號 someaccount\n", f"帳號 {P}\n")
case("no-op text returns unchanged", "普通的新聞稿內文", "普通的新聞稿內文")


def main() -> int:
    failed = 0
    for name, src, want in CASES:
        got, _ = R.redact_text(src)
        if got != want:
            failed += 1
            print(f"FAIL  {name}\n      src ={src!r}\n      want={want!r}\n      got ={got!r}")
        else:
            print(f"ok    {name}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
