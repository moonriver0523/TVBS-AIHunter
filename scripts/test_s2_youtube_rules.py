# -*- coding: utf-8 -*-
"""D23 Phase 5：active rule／prompt wording contract。"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(relative):
    with open(os.path.join(ROOT, relative), encoding="utf-8") as f:
        return f.read()


def test_active_rules_describe_d23_round_policy_and_safety_gate():
    rules = read("common/13c-S2-執行版-上-入口與三站擷取.md")
    v9_rules = read("common/v9/13c-S2-執行版-上-入口與三站擷取.md")
    assert "D23" in rules
    assert "CNA → YNA" in rules
    assert "本輪不掃 CNA／YNA（D23）" in rules
    assert "YNA-<videoId>" in rules
    assert "CNA-<videoId>" in rules
    assert "不接正式排程" in rules
    assert "不跑 yt-dlp" in rules
    assert "D23" in v9_rules


def test_active_prompt_points_to_dry_run_tail_without_touching_existing_launcher():
    prompt = read("scripts/s2_scan_prompt.md")
    assert "D23 YouTube" in prompt
    assert "CNA → YNA" in prompt
    assert "--dry-run" in prompt
    assert "s2_scan.ps1" in prompt
    assert "不改" in prompt
    closing = read("common/13c3-S2-執行版-下-收工與防卡.md")
    assert "CNA A／YNA B" in closing


def test_close_then_d23_then_render_order_is_explicit():
    closing = read("common/13c3-S2-執行版-下-收工與防卡.md")
    close_at = closing.index("D23 YouTube")
    render_at = closing.index("s2_render.py")
    assert close_at < render_at
    assert "五站瀏覽器收工硬步驟後" in closing


def main():
    tests = [test_active_rules_describe_d23_round_policy_and_safety_gate,
             test_active_prompt_points_to_dry_run_tail_without_touching_existing_launcher,
             test_close_then_d23_then_render_order_is_explicit]
    ok = True
    for test in tests:
        try:
            test()
            print(f"[PASS] {test.__name__}")
        except Exception as exc:
            ok = False
            print(f"[FAIL] {test.__name__} — {exc!r}")
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
