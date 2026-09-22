#Requires -Version 7
<#
.SYNOPSIS
  一鍵回滾 2026-09-22 上線的 build 內建機械autofix（MASTER A12「(BITE)/SOT自動導出」子項）。

.DESCRIPTION
  把 s2_batch_prep.py 還原成上線前的版本（備份於 scripts/_rollback/
  s2_batch_prep.py.pre-autofix-20260922.bak），不需要記 git commit hash。
  還原後會自動 git commit 一筆，方便追溯。

.EXAMPLE
  pwsh -File E:\GitHub\TVBS-AIHunter\scripts\s2_rollback_autofix_build.ps1
#>
[CmdletBinding()]
param(
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [switch]$NoCommit
)

$ErrorActionPreference = 'Stop'
$backup = Join-Path $Repo 'scripts\_rollback\s2_batch_prep.py.pre-autofix-20260922.bak'
$target = Join-Path $Repo 'scripts\s2_batch_prep.py'

if (-not (Test-Path $backup)) {
    Write-Error "找不到回滾備份檔：$backup"
    exit 1
}

Copy-Item -LiteralPath $backup -Destination $target -Force
Write-Host "✅ 已還原 $target 為 2026-09-22 上線前版本（build不再內建自動修補）"

if (-not $NoCommit) {
    Push-Location $Repo
    try {
        git add scripts/s2_batch_prep.py
        $status = git status --short scripts/s2_batch_prep.py
        if ($status) {
            git commit -m "revert(s2): 一鍵回滾 build 內建機械autofix（MASTER A12子項）`n`n觀察後決定回退，改用 scripts/s2_rollback_autofix_build.ps1 還原。"
            Write-Host "✅ 已 commit 回滾"
        } else {
            Write-Host "ℹ️ 檔案內容跟上次 commit 一致，沒有變更可 commit"
        }
    } finally {
        Pop-Location
    }
}
