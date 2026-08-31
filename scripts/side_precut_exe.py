# -*- coding: utf-8 -*-
"""側錄初處理——獨立打包（PyInstaller）用的進入點。

只開側錄初處理，不掛掐BITE（`bite_workbench.build_app(..., precut_only=True)`）。
給沒裝 Python 的其他機器用；ffmpeg/ffprobe 隨 exe 一起放在 `bin/` 資料夾（打包腳本
`scripts/build_side_precut_exe.ps1` 負責複製），啟動時把 `bin/` 加進 PATH，
不需要另外裝 ffmpeg。NLLB 中文翻譯是選配——那台機器沒裝本機 NLLB 就自動 fallback
留英文原文（`side_precut.nllb_map` 既有行為），不會讓程式壞掉。
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _bootstrap_ffmpeg_path() -> None:
    bin_dir = os.path.join(_app_dir(), "bin")
    if os.path.isdir(bin_dir):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


def main() -> int:
    _bootstrap_ffmpeg_path()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import uvicorn
    import bite_workbench as BW

    host = "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    default_dir = sys.argv[1] if len(sys.argv) > 1 else None
    app = BW.build_app(default_dir, precut_only=True)
    threading.Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    print(f"側錄初處理 → http://{host}:{port}（關掉這個黑窗就是關伺服器）")
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
