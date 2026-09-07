#Requires -Version 7
<#
.SYNOPSIS
  S2 掃帶規則 V8（五層合一）→ V8 之前一鍵回滾。預設唯讀，加 -WhatIf 只看清單。

.DESCRIPTION
  2026-09-07 A26 把 `13c`／`13c2`／`13d`／`13g`／`13h` 五份「疊層」執行版合一成
  單層四檔（`13c`／`13c1`／`13c1b`／`13c2`／`13c3`），舊五檔搬到
  `common/_rules_backup_20260907/`，並改了 `s2_rules_check.py`／
  `s2_token_metrics.py`／`s2_scan_prompt.md`／`s2_scan_prompt_v7.md`。

  如果 V8 上線後輪次出問題，跑這一支：
    1. 從 `common/_rules_backup_20260907/` 還原五份原檔到 `common/`
    2. 刪除 V8 新增的四份執行版＋歸檔附錄
    3. 用 `git checkout <V8 上線前 commit> -- <這些檔>` 還原
       `s2_rules_check.py`／`s2_token_metrics.py`／`s2_scan_prompt.md`／
       `s2_scan_prompt_v7.md`／`13f-S2-大分類與各站規則.md`
       （`13f` 尾的收工清單總表被 V8 搬進 `13c3`，回滾要把 `13f` 也還原回長版本）
    4. 提醒：`s2_v5_switch.ps1`／`s2_v7_switch.ps1`／`s2_rules_rollback.ps1`
       還躺在 `scripts/_archive/`，回滾後要用的話自己搬回來（本腳本不動它們，
       避免回滾一半又再次改動 repo 結構）。

  ⚠️ 生效時機：規則是**每輪開跑時**從 repo 現讀的，回滾後**下一輪自動生效**，
     不必重啟排程、看門狗或保活。但**輪次進行中不要跑**。

.PARAMETER PreV8Commit
  V8 上線前的 commit（短 hash 或全 hash）。預設 `b9858c1`（Task 1 完成、
  Task 2 開始前的最後一個 commit）。git checkout 用這個版本還原被 V8
  改過的腳本／13f。

.EXAMPLE
  pwsh -File scripts\s2_rules_rollback_v8.ps1              # 看狀態（唯讀）
  pwsh -File scripts\s2_rules_rollback_v8.ps1 -WhatIf       # 只印清單，不動檔
  pwsh -File scripts\s2_rules_rollback_v8.ps1               # 真的回滾（需再次確認）
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [string]$PreV8Commit = 'b9858c1',
    # 略過「是否有輪次在跑」的檢查（只有你確定安全時才用）
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$backup = Join-Path $Repo 'common\_rules_backup_20260907'

Write-Host '=== S2 規則檔回滾（V8 五層合一 → V8 之前）===' -ForegroundColor Cyan

if (-not (Test-Path $backup)) {
    Write-Host "❌ 找不到備份資料夾：$backup" -ForegroundColor Red
    Write-Host "   改用 git：git checkout $PreV8Commit -- common/13*.md scripts/s2_*.py scripts/s2_scan_prompt*.md"
    exit 2
}

# ── 有沒有輪次正在跑 ────────────────────────────────────────────────
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

# ── 還原五份原檔（從 backup 複製回 common/） ────────────────────────
$restoreNames = @(
    '13c-S2-定時掃帶-v3省token.md',
    '13c2-S2-定時掃帶-v3省token-下.md',
    '13d-S2-定時掃帶-v4.md',
    '13g-S2-定時掃帶-v5-四站.md',
    '13h-S2-定時掃帶-v7-五站.md'
)
foreach ($name in $restoreNames) {
    $src = Join-Path $backup $name
    $dst = Join-Path $Repo 'common' $name
    if (-not (Test-Path $src)) { Write-Host "⚠️ 備份缺 $name，略過" -ForegroundColor Yellow; continue }
    if ($PSCmdlet.ShouldProcess($dst, '還原（V8 之前的五份原檔）')) {
        Copy-Item $src $dst -Force
        Write-Host "  ✅ 還原 $name"
    }
}

# ── 刪掉 V8 新增的四份執行版＋歸檔附錄 ──────────────────────────────
$v8New = @(
    '13c-S2-執行版-上-入口與三站擷取.md',
    '13c1-S2-執行版-中-ENEX.md',
    '13c1b-S2-執行版-中-ABC.md',
    '13c2-S2-執行版-下-狀態檔與指令.md',
    '13c3-S2-執行版-下-收工與防卡.md',
    '13c-V8-已取代條文.md'
)
foreach ($gone in $v8New) {
    $p = Join-Path $Repo 'common' $gone
    if (Test-Path $p) {
        if ($PSCmdlet.ShouldProcess($p, '刪除（V8 產物）')) {
            Remove-Item $p -Force
            Write-Host "  ✅ 刪除 $gone"
        }
    }
}

# ── git checkout 還原被 V8 改過的腳本／13f ──────────────────────────
$gitFiles = @(
    'scripts/s2_rules_check.py',
    'scripts/s2_token_metrics.py',
    'scripts/s2_scan_prompt.md',
    'scripts/s2_scan_prompt_v7.md',
    'scripts/s2_reclass_prompt.md',
    'common/13f-S2-大分類與各站規則.md',
    'common/18-交換平台素材整併.md',
    'common/20260812-S2省Token優化計畫-修訂版.md',
    'common/13-S2-定時掃帶.md'
)
if ($PSCmdlet.ShouldProcess("git checkout $PreV8Commit", ($gitFiles -join ', '))) {
    Push-Location $Repo
    try {
        & git checkout $PreV8Commit -- $gitFiles
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ git checkout 失敗（exit $LASTEXITCODE）——確認 $PreV8Commit 是正確的 V8 上線前 commit" -ForegroundColor Red
            exit 5
        }
        Write-Host "  ✅ git checkout $PreV8Commit -- 這 $($gitFiles.Count) 個檔"
    } finally {
        Pop-Location
    }
}

Write-Host ''
Write-Host '📌 scripts/_archive/ 裡的 s2_v5_switch.ps1／s2_v7_switch.ps1／' -ForegroundColor Yellow
Write-Host '   s2_rules_rollback.ps1 沒有被搬回來——回滾後要用版本切換制的話自己搬。' -ForegroundColor Yellow

if ($WhatIfPreference) { Write-Host '（-WhatIf：以上都沒有真的執行）' -ForegroundColor Yellow; exit 0 }

# ── 驗證 ────────────────────────────────────────────────────────────
Push-Location $Repo
try {
    & python -X utf8 scripts\s2_rules_check.py --quiet
    $checkExit = $LASTEXITCODE
} finally {
    Pop-Location
}
Write-Host ''
if ($checkExit -eq 0) {
    Write-Host '✅ 回滾完成：s2_rules_check.py 通過' -ForegroundColor Green
} else {
    Write-Host "❌ 回滾後 s2_rules_check.py 仍未通過（exit $checkExit），請人工確認" -ForegroundColor Red
    exit 4
}
Write-Host '📌 下一輪掃帶自動生效，不必重啟任何東西。'
Write-Host '📌 回滾只動工作區檔案，沒有 commit。要一併回退版控：'
Write-Host ('     git -C "' + $Repo + '" add -A common scripts; git commit -m "rollback: 還原 V8 五層合一前規則"')
