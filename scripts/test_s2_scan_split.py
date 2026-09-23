import locale
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "s2_scan.ps1"

# pwsh 的早期 Write-Host（DryRun/參數驗證的 throw）發生在腳本自己的
# UTF-8 主控台編碼修正之前，實際輸出的是本機主控台字碼頁（在繁中
# Windows 常是 Big5/950，不是 UTF-8）。用系統偏好編碼解碼，並容錯
# 無法對應的位元組，避免這支測試本身因為機器字碼頁不同而誤判失敗。
_CONSOLE_ENCODING = locale.getpreferredencoding(False)


class SplitSessionLauncherTests(unittest.TestCase):
    def run_dry(self, split: bool) -> tuple[subprocess.CompletedProcess[str], Path]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        state = root / "state"
        logs = root / "logs"
        telemetry = root / "telemetry"
        state.mkdir()
        args = [
            "pwsh", "-NoProfile", "-File", str(LAUNCHER),
            "-DryRun", "-Checkpoint", "0923-1700",
            "-RunId", "00000000-0000-4000-8000-000000000041",
            "-StateDir", str(state), "-LogDir", str(logs),
            "-TelemetryDir", str(telemetry),
            "-LockFile", str(root / "scan.lock"),
            "-Provider", "claude",
        ]
        if split:
            args.append("-SplitSession")
        result = subprocess.run(
            args, cwd=HERE.parent, text=True, encoding=_CONSOLE_ENCODING, errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
        )
        return result, logs

    def test_default_dry_run_never_enters_manifest_path(self):
        result, logs = self.run_dry(split=False)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertNotIn("s2_round_manifest.py", result.stdout)
        self.assertNotIn("SplitSession：", result.stdout)
        self.assertEqual([], list(logs.glob("round-*.json")))

    def test_split_dry_run_shows_two_scoped_sessions_without_writing_manifest(self):
        result, logs = self.run_dry(split=True)
        self.assertEqual(0, result.returncode, result.stdout)
        expected = [
            "--session core:NS,AP,RT --session platform:ENEX,ABC",
            "[core] start-session → claude -p（限 NS,AP,RT）→ finish-session",
            "[platform] start-session → claude -p（限 ENEX,ABC）→ finish-session",
            "assert-complete → start-finalize → set-top/set-run → s2_render.py → finish-finalize",
        ]
        positions = [result.stdout.index(text) for text in expected]
        self.assertEqual(sorted(positions), positions)
        self.assertEqual([], list(logs.glob("round-*.json")))

    def test_split_rejects_non_five_site_checkpoint(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        args = [
            "pwsh", "-NoProfile", "-File", str(LAUNCHER), "-DryRun",
            "-SplitSession", "-Checkpoint", "0923-2000",
            "-RunId", str(uuid.uuid4()), "-StateDir", str(root / "state"),
            "-LogDir", str(root / "logs"), "-TelemetryDir", str(root / "telemetry"),
            "-LockFile", str(root / "scan.lock"), "-Provider", "claude",
        ]
        (root / "state").mkdir()
        result = subprocess.run(
            args, cwd=HERE.parent, text=True, encoding=_CONSOLE_ENCODING, errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("只適用五站輪", result.stdout)

    def test_scoped_prompts_override_full_round_work(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        for contract in [
            "本次只處理 NS → AP → RT",
            "禁止掃描、擷取或整併 ENEX／ABC",
            "本次只處理 ENEX → ABC",
            "禁止重掃 NS／AP／RT",
            "禁止 set-top、set-run、s2_render.py",
            "$sessionArgs[1] = $scopePrompt",
        ]:
            self.assertIn(contract, source)


if __name__ == "__main__":
    unittest.main()
