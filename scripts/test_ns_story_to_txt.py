"""ns_story_to_txt.py 反例測試：python -X utf8 scripts/test_ns_story_to_txt.py"""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ns_story_to_txt as m  # noqa: E402

SCRIPT_HTML = (
    "<p><pi><b>This package contains content from Joseph Sais.</b></pi></p>"
    "<p></p>"
    "<p><b>*EDITORIAL INFORMATION PROVIDED BY KCRA </b></p>"
    "<p></p>"
    "<p><b>--SUPERS--</b></p>"
    "<p>Sunday</p>"
    "<p>Steven Murphie</p>"
    "<p>Attendee</p>"
    "<p></p>"
    "<p><b>--REPORTER PKG-AS FOLLOWS</b>--</p>"
    "<p>&quot;I want to feel safe,&quot; said Murphie. It&rsquo;s fine.</p>"
    "<p>Steven Murphie: We love it here.</p>"
)


def item(**kw):
    base = dict(id="WE-003MO", title="CA: RAINBOW", description="desc", owner=["KCRA", "Joseph Sais"],
                embargo=["THIRD PARTY"], footageType="DONUT", duration=109000, reporter="Esteban Reynoso",
                createdDate="2026-09-07T06:02:00.000Z", script=SCRIPT_HTML)
    base.update(kw)
    return base


def test_html_to_text():
    t = m.html_to_text(SCRIPT_HTML)
    lines = t.split("\n")
    assert "--SUPERS--" in lines, lines                      # 粗體標籤不可把 --SUPERS-- 切成兩行
    assert "--REPORTER PKG-AS FOLLOWS--" in lines, lines
    assert "*EDITORIAL INFORMATION PROVIDED BY KCRA" in lines  # 行尾空白去掉
    assert '"I want to feel safe," said Murphie. It’s fine.' in lines  # 實體解碼
    assert "<" not in t and ">" not in t
    assert "\n\n\n" not in t


def test_trt_and_lists():
    assert m.fmt_trt(109000) == "01:49"
    assert m.fmt_trt(66000) == "01:06"
    assert m.fmt_trt(None) == ""
    assert m.join_list(["Pool", "Apple TV"]) == "Pool, Apple TV"
    assert m.join_list("NONE") == "NONE"


def test_pick_newest_and_others():
    old = item(title="OLD RENNER", createdDate="2024-01-01T07:00:00.000Z")
    new = item(title="NEW PSA", createdDate="2026-09-07T06:00:00.000Z")
    other = item(id="PY-02MO", title="NOT ME")
    chosen, others = m.pick([old, other, new], "py-01mo".upper() if False else "WE-003MO")
    assert chosen["title"] == "NEW PSA"
    assert [o["title"] for o in others] == ["OLD RENNER"]
    assert m.pick([other], "WE-003MO") == (None, [])


def test_build_txt_header_matches_existing_format():
    txt = m.build_txt(item())
    head = txt.split("\n\n", 1)[0].split("\n")
    assert head == [
        "Story Number: WE-003MO", "Title: CA: RAINBOW", "Description: desc", "Source: KCRA, Joseph Sais",
        "Embargo: THIRD PARTY", "Footage Type: DONUT", "TRT: 01:49", "Reporter: Esteban Reynoso",
    ]
    assert txt.endswith("We love it here.\n")


def test_main_exit_codes(capsys):
    with tempfile.TemporaryDirectory() as d:
        j = Path(d) / "x.json"
        out = Path(d) / "WE-003MO 原始文稿.txt"
        j.write_text(json.dumps([item(), item(title="OLD", createdDate="2024-01-01T00:00:00Z")]), encoding="utf-8")
        assert m.main(["--json", str(j), "--id", "WE-003MO", "--out", str(out)]) == 0
        cap = capsys.readouterr().out
        assert "另有 1 則" in cap and "OLD" in cap
        assert out.read_text(encoding="utf-8").startswith("Story Number: WE-003MO")
        # 0 則 → exit 2
        j.write_text(json.dumps([item(id="PY-02MO")]), encoding="utf-8")
        assert m.main(["--json", str(j), "--id", "WE-003MO", "--out", str(out)]) == 2
        # 舊素材警告
        stale = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        j.write_text(json.dumps([item(createdDate=stale)]), encoding="utf-8")
        assert m.main(["--json", str(j), "--id", "WE-003MO", "--out", str(out)]) == 0
        assert "距今" in capsys.readouterr().out
        # 空 script 警告
        j.write_text(json.dumps([item(script="<p></p>")]), encoding="utf-8")
        m.main(["--json", str(j), "--id", "WE-003MO", "--out", str(out)])
        assert "script 為空" in capsys.readouterr().out


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
