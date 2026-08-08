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
    [string]$LogFile = 'D:\Downloads\S2掃帶log\_NS保活.log',

    # ntfy.sh 推播頻道。**刻意放在 repo 外**——頻道名等於密碼（知道的人都能訂閱／發送），
    # 不該進版控。檔案不存在＝不推播，其餘功能照跑。
    [string]$TopicFile = "$env:USERPROFILE\.s2-ntfy-topic",
    # 每站的登入態記憶，用來只在「狀態改變」時推播（見下方 Notify-IfChanged）
    [string]$StateFile = "$env:USERPROFILE\.s2-login-state.json"
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

function Log([string]$line) {
    "$stamp`t$line" | Add-Content -Path $LogFile -Encoding UTF8
    Write-Host $line
}

function Push-Ntfy([string]$body, [string]$title, [string]$tags, [string]$priority) {
    if (-not (Test-Path $TopicFile)) { return }
    $topic = (Get-Content $TopicFile -Raw).Trim()
    if (-not $topic) { return }
    try {
        # ⚠️ HTTP 標頭只吃 ASCII，中文一律放 body（body 是 UTF-8，沒問題）
        Invoke-RestMethod -Uri "https://ntfy.sh/$topic" -Method Post `
            -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
            -Headers @{ Title = $title; Tags = $tags; Priority = $priority } `
            -TimeoutSec 20 | Out-Null
    } catch {
        # ⛔ 推播失敗**絕不可以讓保活整支掛掉**——保活本身比通知重要得多
        Log "WARN 推播失敗（不影響保活）：$($_.Exception.Message)"
    }
}

# 決策邏輯拆在 s2_notify.ps1（純函式、可測，理由見該檔）。這裡只做 IO。
. "$PSScriptRoot\s2_notify.ps1"

function Notify-IfChanged([hashtable]$now) {
    $prev = @{}
    if (Test-Path $StateFile) {
        try {
            (Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties |
                ForEach-Object {
                    $v = $_.Value
                    $prev[$_.Name] = @{
                        streak = [int]$v.streak
                        notified = [bool]$v.notified
                    }
                }
        } catch {
            Log "WARN 登入態記憶讀檔失敗，當成全新開始：$($_.Exception.Message)"
        }
    }
    $r = Get-NotifyActions -Now $now -Prev $prev
    foreach ($p in $r.Pushes) {
        Push-Ntfy $p.Body $p.Title $p.Tags $p.Priority
        Log $p.Log
    }
    try {
        $r.Next | ConvertTo-Json -Depth 4 | Set-Content -Path $StateFile -Encoding UTF8
    } catch {
        Log "WARN 登入態記憶寫檔失敗：$($_.Exception.Message)"
    }
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

    # 從輸出解析每站狀態，例：`NS=OK(3592s) AP=LOGGED_OUT RT=OK secs=24.0`
    $now = @{}
    foreach ($m in [regex]::Matches($out, '\b(NS|AP|RT)=(OK|LOGGED_OUT|ERR)')) {
        $now[$m.Groups[1].Value] = $m.Groups[2].Value
    }

    switch ($code) {
        0 { Log "OK   $out" }
        3 {
            # ⚠️ 這行原本寫死「NS 已登出」，但掛的是 AP／RT 時也照印 NS——
            # 讀 log 的人會判斷錯站別（0808 一整晚的 `*** NS 已登出 *** AP=LOGGED_OUT`
            # 就是這樣來的）。改成印**真正掛掉的那幾站**。
            $down = ($now.Keys | Where-Object { $now[$_] -eq 'LOGGED_OUT' } | Sort-Object) -join '／'
            if (-not $down) { $down = '（解析不出站別）' }
            Log "*** $down 已登出，需要人工重新登入 *** $out"
        }
        default { Log "ERR  離開碼=$code $out" }
    }

    if ($now.Count) { Notify-IfChanged $now }
    exit $code
}
finally {
    if ($lock) { $lock.Dispose() }
}
