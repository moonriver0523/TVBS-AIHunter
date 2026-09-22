#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s2_finalize_shadow.py 唯讀與 fail-open 單元測試。"""
import importlib.util
import json
import os
import tempfile
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    "shadow", os.path.join(HERE, "s2_finalize_shadow.py"))
shadow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shadow)


def tool_line(call_id, command):
    return json.dumps({
        "timestamp": "2026-09-22T16:00:00Z",
        "message": {"content": [{
            "type": "tool_use", "id": call_id, "name": "Bash",
            "input": {"command": command},
        }]},
    }, ensure_ascii=False)


class FinalizeShadowTest(unittest.TestCase):
    def test_normal_data_produces_comparison_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "0922-s2-state.json")
            log_path = os.path.join(tmp, "掃帶log-0922-2359-test.txt")
            state = {
                "checkpoint": "0922-2359",
                "reconcile_log": {
                    "0922-2359": {"RT": {}, "AP": {}, "NS": {}},
                },
                "items": [],
            }
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False)
            calls = [
                tool_line("pre", "python scripts/s2_state.py resume"),
                tool_line("a1", "python scripts/s2_audit.py --mmdd 0922 --rt-list r --ap-list a --ns-list n"),
                tool_line("p1", "python scripts/s2_platform_reconcile.py --site enex"),
                tool_line("r1", "python scripts/s2_render.py --file state.json"),
                tool_line("v1", "python scripts/s2_state.py --file state.json resume"),
            ]
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(calls) + "\n")
            with open(state_path, "rb") as handle:
                state_before = handle.read()
            with open(log_path, "rb") as handle:
                log_before = handle.read()

            report = shadow.build_report(state_path, log_path)

            self.assertIn("預期工具呼叫：約 3–5 次", report)
            self.assertIn("其中 audit/reconcile/render/驗證：4 次", report)
            self.assertIn("已記錄：RT／AP／NS", report)
            with open(state_path, "rb") as handle:
                self.assertEqual(state_before, handle.read())
            with open(log_path, "rb") as handle:
                self.assertEqual(log_before, handle.read())

    def test_missing_or_broken_data_is_fail_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken_log = os.path.join(tmp, "broken.txt")
            with open(broken_log, "w", encoding="utf-8") as handle:
                handle.write("not-json\n")

            report = shadow.build_report(
                os.path.join(tmp, "missing-state.json"), broken_log)
            self.assertIn("【警告（fail-open）】", report)
            self.assertIn("狀態檔讀取失敗", report)
            self.assertIn("找不到 tool_use", report)
            self.assertEqual(0, shadow.main([
                "--state", os.path.join(tmp, "missing-state.json"),
                "--log", os.path.join(tmp, "missing-log.txt"),
            ]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
