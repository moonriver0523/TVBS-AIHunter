#Requires -Version 7
<#
.SYNOPSIS
  S2 掃帶 prompt V8 ⇄ T14 平行 tool-call canary 一鍵切換。預設唯讀，只印狀態。

.DESCRIPTION
  管理單一 live 檔案 scripts\s2_scan_prompt.md：

  - canary 來源：common\parallel\s2_scan_prompt.md
  - V8 備份：common\parallel\_orig_bak\s2_scan_prompt.md
  - 分叉基準：common\parallel\FORK-BASE.txt（sha256；行尾正規化成 LF）

  -On 前會擋下 V8 fork-base 漂移；-On／-Off 都會偵測掃帶鎖與程序、切換後執行
  s2_rules_check.py，檢查失敗即把 live 檔還原成切換前內容。-Force 只略過忙碌、
  fork-base 漂移或 canary 手改保護，不略過 rules_check。

  本切換器只改 prompt，不改五站規則與 state。切換後下一輪才會讀到新 prompt。

.EXAMPLE
  pwsh -File scripts\s2_parallel_switch.ps1          # 看狀態（唯讀）
  pwsh -File scripts\s2_parallel_switch.ps1 -On      # 切到 canary
  pwsh -File scripts\s2_parallel_switch.ps1 -Off     # 退回 V8
#>
[CmdletBinding()]
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Force,
    [string]$Repo = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$name     = 's2_scan_prompt.md'
$live     = Join-Path $Repo 'scripts\s2_scan_prompt.md'
$parallel = Join-Path $Repo 'common\parallel'
$source   = Join-Path $parallel $name
$bakdir   = Join-Path $parallel '_orig_bak'
$backup   = Join-Path $bakdir $name
$forkf    = Join-Path $parallel 'FORK-BASE.txt'
$lock     = "$env:USERPROFILE\.s2-scan.lock"
$check    = Join-Path $Repo 'scripts\s2_rules_check.py'
$marker   = '<!-- S2-PARALLEL-CANARY -->'

# autocrlf 會改位元組；與既有 switch 慣例一致，雜湊前先把 CRLF 正規化成 LF。
function Sha([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $text = [System.IO.File]::ReadAllText($Path).Replace(
        ([string][char]13 + [string][char]10),
        [string][char]10
    )
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }
    finally { $sha.Dispose() }
}

function Get-ForkBase {
    if (-not (Test-Path -LiteralPath $forkf)) { return $null }
    foreach ($line in [System.IO.File]::ReadAllLines($forkf)) {
        $parts = $line -split '\s+'
        if ($parts.Count -ge 2 -and $parts[1] -eq $name) { return $parts[0] }
    }
    return $null
}

function Has-CanaryMarker([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return [System.IO.File]::ReadAllText($Path).Contains($marker)
}

function Get-LiveVersion {
    if (-not (Test-Path -LiteralPath $live)) { return 'MISSING' }
    if (Has-CanaryMarker $live) {
        if ((Test-Path -LiteralPath $source) -and (Sha $live) -eq (Sha $source)) {
            return 'CANARY'
        }
        return 'CANARY-DRIFT'
    }
    return 'V8'
}

# 只看 lock 是否存在，絕不開 lock；另查是否有 s2_scan.ps1 程序。
function Test-Busy {
    if (Test-Path -LiteralPath $lock) { return $true }
    $running = @(Get-CimInstance Win32_Process -Filter "Name='pwsh.exe' OR Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 's2_scan\.ps1' })
    return ($running.Count -gt 0)
}

function Invoke-RulesCheck {
    # Out-Host 避免 stdout 混進函式回傳值；python 叫不起來也視為失敗，交給呼叫端回滾。
    try {
        & python -X utf8 $check --quiet | Out-Host
        return $LASTEXITCODE
    }
    catch {
        Write-Host "❌ 無法執行 rules_check：$($_.Exception.Message)" -ForegroundColor Red
        return 99
    }
}

function Restore-Bytes([byte[]]$Bytes) {
    [System.IO.File]::WriteAllBytes($live, $Bytes)
}

function Show-Status {
    $version = Get-LiveVersion
    $fork = Get-ForkBase
    Write-Host ''
    Write-Host '== S2 prompt 平行 tool-call canary 狀態 ==' -ForegroundColor Cyan
    Write-Host "生效中      : $version"
    Write-Host "live        : $live"
    Write-Host "canary 來源 : $(if (Test-Path -LiteralPath $source) { 'OK' } else { '❌缺檔' })"
    Write-Host "V8 備份     : $(if (Test-Path -LiteralPath $backup) { 'OK' } else { '❌缺檔' })"
    Write-Host "fork-base   : $(if ($fork) { $fork } else { '❌缺基準' })"

    if ($version -eq 'V8' -and $fork) {
        if ((Sha $live) -eq $fork) {
            Write-Host 'V8 漂移     : 無' -ForegroundColor Green
        }
        else {
            Write-Host 'V8 漂移     : ⚠️ 自 canary 分叉後已修改；-On 前先同步 canary' -ForegroundColor Yellow
        }
    }
    elseif ($version -eq 'CANARY-DRIFT') {
        Write-Host 'canary 漂移 : ⚠️ live 含 canary 標記，但內容不同於來源' -ForegroundColor Yellow
    }

    Write-Host "掃帶狀態    : $(if (Test-Busy) { '⚠️ 有鎖檔或 s2_scan.ps1 在跑' } else { '空閒' })"
    Write-Host ''
}

if ($On -and $Off) {
    Write-Host '❌ -On 與 -Off 只能擇一' -ForegroundColor Red
    exit 1
}
if (-not $On -and -not $Off) {
    Show-Status
    exit 0
}

if ((Test-Busy) -and -not $Force) {
    Write-Host '⚠️ 輪次可能正在跑。等跑完再切；確定要切請加 -Force。' -ForegroundColor Yellow
    exit 1
}

if ($On) {
    $cur = Get-LiveVersion
    if ($cur -eq 'CANARY') {
        Write-Host '已經是 canary，不必再切。' -ForegroundColor Green
        exit 0
    }
    if ($cur -ne 'V8') {
        Write-Host "❌ 目前 live 是 $cur，不是可安全切換的 V8。" -ForegroundColor Red
        exit 1
    }

    foreach ($required in @($live, $source, $backup, $forkf, $check)) {
        if (-not (Test-Path -LiteralPath $required)) {
            Write-Host "❌ 缺必要檔案：$required" -ForegroundColor Red
            exit 1
        }
    }
    if (-not (Has-CanaryMarker $source)) {
        Write-Host "❌ canary 來源缺標記：$marker" -ForegroundColor Red
        exit 1
    }
    if (Has-CanaryMarker $backup) {
        Write-Host '❌ V8 備份誤含 canary 標記，拒絕切換。' -ForegroundColor Red
        exit 1
    }

    $fork = Get-ForkBase
    if (-not $fork) {
        Write-Host "❌ FORK-BASE.txt 沒有 $name 的基準。" -ForegroundColor Red
        exit 1
    }
    if ((Sha $live) -ne $fork -and -not $Force) {
        Write-Host '❌ V8 prompt 自分叉後已修改；先把修正同步到 canary，確定要略過請加 -Force。' -ForegroundColor Red
        exit 1
    }

    $previous = [System.IO.File]::ReadAllBytes($live)
    New-Item -ItemType Directory -Force -Path $bakdir | Out-Null
    Copy-Item -LiteralPath $live -Destination $backup -Force
    Copy-Item -LiteralPath $source -Destination $live -Force

    if ((Invoke-RulesCheck) -ne 0) {
        Restore-Bytes $previous
        Write-Host '❌ 切到 canary 後 rules_check 未通過，已自動還原切換前的 V8 prompt。' -ForegroundColor Red
        exit 1
    }
    Write-Host '✅ 已切到平行 tool-call canary（下一輪生效）。退回：pwsh -File scripts\s2_parallel_switch.ps1 -Off' -ForegroundColor Green
    exit 0
}

if ($Off) {
    $cur = Get-LiveVersion
    if ($cur -eq 'V8') {
        Write-Host '已經是 V8，不必再切。' -ForegroundColor Green
        exit 0
    }
    if ($cur -eq 'CANARY-DRIFT' -and -not $Force) {
        Write-Host '❌ live canary 已被手改；先 diff 確認，確定用 V8 備份覆蓋請加 -Force。' -ForegroundColor Red
        exit 1
    }
    if ($cur -notin @('CANARY', 'CANARY-DRIFT')) {
        Write-Host "❌ 目前 live 是 $cur，不是可回退的 canary。" -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path -LiteralPath $backup)) {
        Write-Host "❌ 缺 V8 備份：$backup" -ForegroundColor Red
        exit 1
    }
    if (Has-CanaryMarker $backup) {
        Write-Host '❌ V8 備份含 canary 標記，拒絕覆蓋 live。' -ForegroundColor Red
        exit 1
    }

    $previous = [System.IO.File]::ReadAllBytes($live)
    Copy-Item -LiteralPath $backup -Destination $live -Force

    if ((Invoke-RulesCheck) -ne 0) {
        Restore-Bytes $previous
        Write-Host '❌ 退回 V8 後 rules_check 未通過，已自動還原切換前的 canary prompt。' -ForegroundColor Red
        exit 1
    }
    Write-Host '✅ 已退回 V8（下一輪生效）。' -ForegroundColor Green
    exit 0
}
