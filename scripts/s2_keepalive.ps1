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
    [string]$StateFile = "$env:USERPROFILE\.s2-login-state.json",

    # chromium 的 cookie 資料庫。**保活前後各量一次**（2026-08-09 蒐證用）：
    # 使用者與我都懷疑「AP 掉線＝關閉時 cookie 沒寫回磁碟」，而這件事**可以直接量**，
    # 不必猜——關乾淨的話這個檔的修改時間會往前走，沒動就是沒寫回去。
    [string]$CookieDb = "$env:USERPROFILE\.playwright-mcp-profile\Default\Network\Cookies"
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

function Log([string]$line) {
    "$stamp`t$line" | Add-Content -Path $LogFile -Encoding UTF8
    Write-Host $line
}

function Push-Ntfy([string]$body, [string]$title, [string]$tags, [string]$priority) {
    # 實作在 s2_notify.ps1（掃帶收工也要推播，兩邊共用一份，免得分岔）
    $err = Send-Ntfy -Body $body -Title $title -Tags $tags -Priority $priority -TopicFile $TopicFile
    # ⛔ 推播失敗**絕不可以讓保活整支掛掉**——保活本身比通知重要得多
    if ($err) { Log "WARN 推播失敗（不影響保活）：$err" }
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
                        last = [string]$v.last
                    }
                }
        } catch {
            Log "WARN 登入態記憶讀檔失敗，當成全新開始：$($_.Exception.Message)"
        }
    }
    # 蒐證：0809 04:20 保活異常結束（ERR）→ 04:30 掃帶就發現 cookie 不見了。
    # 若「上次 ERR、這次 LOGGED_OUT」反覆出現，就是「關不乾淨→掉線」的直接證據。
    # 只記錄不下結論——**一個樣本不是規律**。
    foreach ($site in $now.Keys) {
        if ($now[$site] -eq 'LOGGED_OUT' -and $prev[$site] -and $prev[$site].last -eq 'ERR') {
            Log "🔎 形狀吻合：$site 上一次是 ERR、這次 LOGGED_OUT（關不乾淨→掉線 的候選證據）"
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
    # 蒐證：關閉時 cookie 到底有沒有寫回磁碟（見 $CookieDb 說明）
    $ckBefore = Get-Item $CookieDb -ErrorAction SilentlyContinue

    $out = node $Script 2>&1 | Out-String
    $code = $LASTEXITCODE
    $out = $out.Trim()

    $ckAfter = Get-Item $CookieDb -ErrorAction SilentlyContinue
    if ($ckBefore -and $ckAfter) {
        $flushed = $ckAfter.LastWriteTime -gt $ckBefore.LastWriteTime
        $delta = $ckAfter.Length - $ckBefore.Length
        $ckNote = "cookie寫回=$(if ($flushed) { 'YES' } else { 'NO' }) 大小差=$delta"
        # 「沒寫回」不必然是壞事（沒有變更就不用寫），所以只記錄不警告——
        # 要的是**累積樣本**，看它跟掉線有沒有相關，而不是當場下結論。
    } else {
        $ckNote = 'cookie檔讀不到'
    }

    # 從輸出解析每站狀態，例：`NS=OK(3592s) AP=LOGGED_OUT RT=OK secs=24.0`
    $now = @{}
    foreach ($m in [regex]::Matches($out, '\b(NS|AP|RT)=(OK|LOGGED_OUT|ERR)')) {
        $now[$m.Groups[1].Value] = $m.Groups[2].Value
    }

    # 蒐證：這次的結果後面接上 cookie 寫回情形
    $out = "$out $ckNote"

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
