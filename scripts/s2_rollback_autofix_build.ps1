#Requires -Version 7
<#
.SYNOPSIS
  一鍵回滾 2026-09-22 上線的 S2 格式防呆改動（build 內建機械autofix＋ENEX/ABC
  操作備註前置檢查＋NS/AP/RT操作備註硬閘降門檻），基準點統一是今天 0100 那輪
  跑的版本（＝這些改動全部上線前）。

.DESCRIPTION
  還原兩支腳本成 0100 版本（備份於 scripts/_rollback/*.pre-autofix-20260922.bak），
  不需要記 git commit hash。還原後會自動 git commit 一筆，方便追溯。

  涵蓋範圍：
    - scripts/s2_batch_prep.py（14:34 上線的build內建autofix＋17:xx新增的
      FMT_OPERATIONAL_NOTE門檻降到1）
    - scripts/s2_platform_extract.py（17:xx新增的ENEX/ABC check-entries
      操作備註前置檢查）
    - scripts/s2_validate.py（17:xx修正「待補」判準避免誤中「產業待補助」
      這類合法內容，Sol code review抓到的regex收緊）

  🔴 2026-09-22 Sol code review：先驗證**全部**備份檔都存在，全部通過才開始
  複製，避免「複製到一半才發現某份備份缺失」造成檔案只還原一半的半套狀態。

.EXAMPLE
  pwsh -File E:\GitHub\TVBS-AIHunter\scripts\s2_rollback_autofix_build.ps1
#>
[CmdletBinding()]
param(
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [switch]$NoCommit
)

$ErrorActionPreference = 'Stop'
$pairs = @(
    @{ Backup = 'scripts\_rollback\s2_batch_prep.py.pre-autofix-20260922.bak'; Target = 'scripts\s2_batch_prep.py' }
    @{ Backup = 'scripts\_rollback\s2_platform_extract.py.pre-autofix-20260922.bak'; Target = 'scripts\s2_platform_extract.py' }
    @{ Backup = 'scripts\_rollback\s2_validate.py.pre-autofix-20260922.bak'; Target = 'scripts\s2_validate.py' }
)

# 先把全部（備份, 目標）絕對路徑解析出來、驗證備份全部存在，任何一份缺失就
# 整體中止、不動任何檔案——不要邊檢查邊複製，那樣第二份缺失時第一份已經被
# 還原，變成半套狀態。
$resolved = foreach ($p in $pairs) {
    $backup = Join-Path $Repo $p.Backup
    $target = Join-Path $Repo $p.Target
    if (-not (Test-Path $backup)) {
        Write-Error "找不到回滾備份檔：$backup（已中止，未還原任何檔案）"
        exit 1
    }
    [pscustomobject]@{ Backup = $backup; Target = $target }
}

foreach ($r in $resolved) {
    Copy-Item -LiteralPath $r.Backup -Destination $r.Target -Force
    Write-Host "✅ 已還原 $($r.Target) 為 2026-09-22 0100 版本（今天所有格式防呆改動全部退回）"
}

if (-not $NoCommit) {
    Push-Location $Repo
    try {
        $targets = $pairs | ForEach-Object { $_.Target }
        git add $targets
        $status = git status --short $targets
        if ($status) {
            git commit -m "revert(s2): 一鍵回滾今天上線的build autofix＋ENEX/ABC/NS/AP/RT操作備註防呆（MASTER A12子項）`n`n觀察後決定回退，改用 scripts/s2_rollback_autofix_build.ps1 還原，基準回到0922-0100版本。"
            Write-Host "✅ 已 commit 回滾"
        } else {
            Write-Host "ℹ️ 檔案內容跟上次 commit 一致，沒有變更可 commit"
        }
    } finally {
        Pop-Location
    }
}
