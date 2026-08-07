#Requires -Version 7
<#
.SYNOPSIS
  NS 保活的排程外殼——跟掃帶共用同一把鎖，撞到就讓掃帶優先。

.DESCRIPTION
  跑 s2_keepalive.js（約 10 秒、零 token），把 NS 那顆 1 小時 JWT 續期。

  **鎖的優先序：掃帶 > 保活。** 兩者共用 `.s2-scan.lock`，因為 Playwright 只有
  一個 persistent profile。撞到時保活**直接放棄**（不重試、不等待）——理由是
  掃帶第一站就是 NS，它自己就會把 token 續掉，保活這一次本來就不必做。

  ⚠️ 反過來絕對不行：保活只握鎖 10 秒，但如果讓它排隊等，就可能卡住一輪
  20 分鐘的掃帶。**寧可漏一次保活，不可漏一輪掃帶。**

.EXAMPLE
  pwsh -NoProfile -File E:\GitHub\TVBS-AIHunter\scripts\s2_keepalive.ps1
#>
[CmdletBinding()]
param(
    [string]$Script = "$PSScriptRoot\s2_keepalive.js",
    [string]$LockFile = "$env:USERPROFILE\.s2-scan.lock",
    [string]$LogFile = 'D:\Downloads\S2掃帶log\_NS保活.log'
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

function Log([string]$line) {
    "$stamp`t$line" | Add-Content -Path $LogFile -Encoding UTF8
    Write-Host $line
}

$lock = $null
try {
    $lock = [System.IO.File]::Open(
        $LockFile, [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch [System.IO.IOException] {
    # 掃帶正在跑＝NS 本來就會被碰到，這次不必做
    Log 'SKIP 掃帶進行中，保活略過（掃帶第一站就是 NS，它會自己續期）'
    exit 0
}

try {
    $out = node $Script 2>&1 | Out-String
    $code = $LASTEXITCODE
    $out = $out.Trim()

    switch ($code) {
        0 { Log "OK   $out" }
        3 {
            # 唯一需要人插手的情況：過期了就沒有任何後備憑證
            Log "*** NS 已登出，需要人工重新登入 *** $out"
        }
        default { Log "ERR  離開碼=$code $out" }
    }
    exit $code
}
finally {
    if ($lock) { $lock.Dispose() }
}
