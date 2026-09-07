# ⛔ 2026-09-07 起停用（它還原的是 2026-08-24 分檔前狀態，V8 後跑它會退回三代前）。改用 scripts/s2_rules_rollback_v8.ps1。
# s2_rules_rollback.ps1 — 一鍵把掃帶規則檔全部還原成 2026-08-24 分檔前的樣子
#
# 用途：2026-08-24 把 `common/13`（1052 行／53,676 字元）切成兩部（`13` ＋ `13e`）
#       並加了 RULES-EOF 標記與 prompt 的載入驗證要求（R15）。
#       如果 0430 之後的輪次出問題，跑這一支就全部還原。
#
# 用法（PowerShell，一行）：
#   pwsh -File E:\GitHub\TVBS-AIHunter\scripts\s2_rules_rollback.ps1
#
# 加 -WhatIf 只看會做什麼、不真的動檔：
#   pwsh -File ...\s2_rules_rollback.ps1 -WhatIf
#
# 還原什麼：
#   common/13-S2-定時掃帶.md          ← 還原成原本 1052 行的完整版
#   common/13c-S2-定時掃帶-v3省token.md
#   common/13d-S2-定時掃帶-v4.md
#   scripts/s2_scan_prompt.md
#   common/13e-S2-素材行與分類規則.md  ← 刪除（分檔產物）
#   common/13f-S2-大分類與各站規則.md  ← 刪除（分檔產物）
#   common/13c2-S2-定時掃帶-v3省token-下.md ← 刪除（分檔產物）
#   common/13-rationale.md            ← 刪除（分檔產物）
#
# ⚠️ 生效時機：規則是**每輪開跑時**從 repo 現讀的，所以還原後**下一輪自動生效**，
#    不必重啟排程、不必重啟 launcher、不必碰 watchdog。
#    但**輪次進行中不要跑**——那一輪已經把舊規則讀進 context 了，換檔沒有意義，
#    而且會讓那一輪的 rule_shas 指紋對不上。

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    # 略過「是否有輪次在跑」的檢查（只有你確定安全時才用）
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$backup = Join-Path $Repo 'common\_rules_backup_20260824'

Write-Host '=== S2 規則檔還原（2026-08-24 分檔 → 分檔前）===' -ForegroundColor Cyan

if (-not (Test-Path $backup)) {
    Write-Host "❌ 找不到備份資料夾：$backup" -ForegroundColor Red
    Write-Host '   改用 git：git checkout rules-pre-slim-20260824 -- common/13*.md scripts/s2_scan_prompt.md'
    exit 2
}

# ── 有沒有輪次正在跑 ────────────────────────────────────────────────
# ⚠️ 不看 .s2-scan.lock：保活腳本共用同一把鎖但不刪檔，鎖檔永遠存在（R16），
#    拿它判斷等於永遠誤報。改看實際行程。
$running = @(Get-CimInstance Win32_Process -Filter "Name='pwsh.exe' OR Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 's2_scan\.ps1' })
if ($running.Count -gt 0) {
    Write-Host "⚠️ 偵測到掃帶輪正在跑（PID: $($running.ProcessId -join ', ')）" -ForegroundColor Yellow
    if (-not $Force) {
        Write-Host '   輪次進行中還原沒有意義（規則已讀進 context），且會讓指紋對不上。'
        Write-Host '   等它跑完再來，或加 -Force 強制執行。'
        exit 3
    }
    Write-Host '   -Force 已指定，繼續。' -ForegroundColor Yellow
}

# ── 還原四個檔 ──────────────────────────────────────────────────────
$restore = @{
    '13-S2-定時掃帶.md'            = Join-Path $Repo 'common'
    '13c-S2-定時掃帶-v3省token.md' = Join-Path $Repo 'common'
    '13d-S2-定時掃帶-v4.md'        = Join-Path $Repo 'common'
    's2_scan_prompt.md'            = Join-Path $Repo 'scripts'
}
foreach ($name in $restore.Keys) {
    $src = Join-Path $backup $name
    $dst = Join-Path $restore[$name] $name
    if (-not (Test-Path $src)) { Write-Host "⚠️ 備份缺 $name，略過" -ForegroundColor Yellow; continue }
    if ($PSCmdlet.ShouldProcess($dst, '還原')) {
        Copy-Item $src $dst -Force
        Write-Host "  ✅ 還原 $name"
    }
}

# ── 刪掉分檔產物 ────────────────────────────────────────────────────
foreach ($gone in @('13e-S2-素材行與分類規則.md', '13f-S2-大分類與各站規則.md',
                     '13c2-S2-定時掃帶-v3省token-下.md', '13-rationale.md')) {
    $p = Join-Path $Repo 'common' $gone
    if (Test-Path $p) {
        if ($PSCmdlet.ShouldProcess($p, '刪除（分檔產物）')) {
            Remove-Item $p -Force
            Write-Host "  ✅ 刪除 $gone"
        }
    }
}

if ($WhatIfPreference) { Write-Host '（-WhatIf：以上都沒有真的執行）' -ForegroundColor Yellow; exit 0 }

# ── 驗證 ────────────────────────────────────────────────────────────
$p13 = Join-Path $Repo 'common\13-S2-定時掃帶.md'
$lines = (Get-Content $p13).Count
Write-Host ''
if ($lines -ge 1000) {
    Write-Host "✅ 還原完成：13 回到 $lines 行（分檔前為 1052 行）" -ForegroundColor Green
} else {
    Write-Host "❌ 還原後 13 只有 $lines 行，不像原始版本，請人工確認" -ForegroundColor Red
    exit 4
}
Write-Host '📌 下一輪掃帶自動生效，不必重啟任何東西。'
Write-Host '📌 還原只動工作區檔案，沒有 commit。要一併回退版控：'
Write-Host '     git -C "' + $Repo + '" add -A common scripts/s2_scan_prompt.md; git commit -m "rollback: 還原 0824 規則分檔"'
