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
    # 小檔遙測放雲端（2026-08-12，跟 s2_scan.ps1 的 -TelemetryDir 一致）
    [string]$LogFile = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log\_NS保活.log',

    # ntfy.sh 推播頻道。**刻意放在 repo 外**——頻道名等於密碼（知道的人都能訂閱／發送），
    # 不該進版控。檔案不存在＝不推播，其餘功能照跑。
    [string]$TopicFile = "$env:USERPROFILE\.s2-ntfy-topic",
    # 每站的登入態記憶，用來只在「狀態改變」時推播（見下方 Notify-IfChanged）
    [string]$StateFile = "$env:USERPROFILE\.s2-login-state.json",

    # chromium 的 cookie 資料庫。**保活前後各量一次**（2026-08-09 蒐證用）：
    # 使用者與我都懷疑「AP 掉線＝關閉時 cookie 沒寫回磁碟」，而這件事**可以直接量**，
    # 不必猜——關乾淨的話這個檔的修改時間會往前走，沒動就是沒寫回去。
    [string]$CookieDb = "$env:USERPROFILE\.playwright-s2-profile-v4\Default\Network\Cookies"
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
# G: 沒掛載就退回本機，不要中斷保活
try { New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) -ErrorAction Stop | Out-Null }
catch {
    Write-Warning "紀錄目錄不可用，改寫本機：$($_.Exception.Message)"
    $LogFile = 'D:\Downloads\S2掃帶log\_NS保活.log'
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
}

# 🔴 寫紀錄不准弄死保活（2026-08-12）：全域是 -ErrorAction Stop，
# 而紀錄檔已改放 Google Drive，同步鎖檔會讓 Add-Content 丟終止性錯誤。
function Log([string]$line) {
    for ($i = 1; $i -le 3; $i++) {
        try { "$stamp`t$line" | Add-Content -Path $LogFile -Encoding UTF8 -ErrorAction Stop; break }
        catch {
            if ($i -eq 3) { Write-Warning "保活寫紀錄失敗（不影響保活）：$($_.Exception.Message)" }
            else { Start-Sleep -Milliseconds (300 * $i) }
        }
    }
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

function Read-LoginState {
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
    return $prev
}

function Write-LoginState([hashtable]$state) {
    try {
        $state | ConvertTo-Json -Depth 4 | Set-Content -Path $StateFile -Encoding UTF8
    } catch {
        Log "WARN 登入態記憶寫檔失敗：$($_.Exception.Message)"
    }
}

function Test-ProfileBusy {
    <#
      profile 正被**別的** chromium 佔用嗎？

      2026-08-10 加。`.s2-scan.lock` 只有掃帶與保活會拿，人／agent 手動開瀏覽器不會拿，
      於是保活會啟第二個 chromium 去搶同一個 user-data-dir，讀不到登入態就誤判成
      `LOGGED_OUT`——0809 22:20／22:50 兩則假警報就是這樣來的（當下 NS token 還有
      3591 秒、RT 也導得進 /all）。

      ⚠️ **比對的是 `--user-data-dir` 路徑，不是行程名**：使用者自己開的 Chrome
      動輒好幾十個 chrome.exe（0810 實測 66 個），只看行程名會全部誤判成佔用。
    #>
    $dir = Split-Path (Split-Path (Split-Path $CookieDb -Parent) -Parent) -Parent
    try {
        $busy = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction Stop |
                Where-Object { $_.CommandLine -and $_.CommandLine.Contains($dir) }
        return [bool]$busy
    } catch {
        # 查不到就**當成沒被佔用**照常跑：保活本來就是要做事的，
        # 為了一個偵測失敗而整晚不續期，代價比偶爾一次假警報大得多。
        Log "WARN profile 佔用偵測失敗，照常執行：$($_.Exception.Message)"
        return $false
    }
}

function Notify-IfChanged([hashtable]$now) {
    $prev = Read-LoginState
    # 蒐證：0809 04:20 保活異常結束（ERR）→ 04:30 掃帶就發現 cookie 不見了。
    # 若「上次 ERR、這次 LOGGED_OUT」反覆出現，就是「關不乾淨→掉線」的直接證據。
    # 只記錄不下結論——**一個樣本不是規律**。
    foreach ($site in $now.Keys) {
        if ($now[$site] -eq 'LOGGED_OUT' -and $prev[$site] -and $prev[$site].last -eq 'ERR') {
            Log "🔎 形狀吻合：$site 上一次是 ERR、這次 LOGGED_OUT（關不乾淨→掉線 的候選證據）"
        }
    }

    $r = Get-NotifyActions -Now $now -Prev $prev
    # 這次真的跑起來了 → 清掉「連續跳過」的計數，必要時回報恢復
    $sk = Get-SkipActions -Skipped $false -Prev $prev
    foreach ($p in ($r.Pushes + $sk.Pushes)) {
        Push-Ntfy $p.Body $p.Title $p.Tags $p.Priority
        Log $p.Log
    }
    $next = $r.Next
    $next['_skip'] = $sk.Next
    Write-LoginState $next
}

function Skip-Run([string]$why) {
    <#
      跳過這一次保活。**SKIP 既不算成功也不算失敗**——各站的 streak／notified
      一律不動（`Get-NotifyActions` 根本不會被呼叫），因為這次沒有觀察到登入態，
      不該拿來推翻或佐證上一次的觀察。

      但**跳過本身要計數**：萬一有 chromium 卡著沒關，保活會永遠跳過、token 到期
      沒人續、而且一聲不響——**靜默失敗比假警報更糟**。連續 4 次（約 2 小時）就推播。
    #>
    Log "SKIP $why"
    $prev = Read-LoginState
    $sk = Get-SkipActions -Skipped $true -Prev $prev
    foreach ($p in $sk.Pushes) {
        Push-Ntfy $p.Body $p.Title $p.Tags $p.Priority
        Log $p.Log
    }
    $prev['_skip'] = $sk.Next
    Write-LoginState $prev
    exit 0
}

$lock = $null
try {
    $lock = [System.IO.File]::Open(
        $LockFile, [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch [System.IO.IOException] {
    # 掃帶正在跑＝NS 本來就會被碰到，這次不必做
    Skip-Run '掃帶進行中，保活略過（掃帶第一站就是 NS，它會自己續期）'
}

# 鎖拿到了，但 profile 仍可能被**沒拿鎖的人**佔著（人工／agent 手動開瀏覽器）。
# 這時硬跑會讀不到登入態、誤判成 LOGGED_OUT 並推假警報（0809 22:20／22:50 實錯）。
if (Test-ProfileBusy) {
    Skip-Run 'profile 被其他 chromium 佔用（有人正在用瀏覽器），保活略過'
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

    # 從輸出解析每站狀態，例：`NS=OK(3592s) ABC=OK AP=LOGGED_OUT RT=OK secs=24.0`
    $now = @{}
    foreach ($m in [regex]::Matches($out, '\b(NS|AP|RT|ABC)=(OK|LOGGED_OUT|ERR)')) {
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
    if ($lock) {
        $lock.Dispose()
        # R16（2026-08-24）：這裡原本只 Dispose 不刪檔，而保活每 30 分鐘跑一次，
        # 鎖檔就永遠躺在那裡 →「檔案存在」與「有沒有輪次在跑」變成零相關，
        # 任何拿它當閘門的程序都是永久誤報。比照 s2_scan.ps1:599 補上刪除。
        # 互斥真正靠的是上面 FileShare::None 的獨佔握把，刪檔只是清留痕；
        # 刪不掉＝已被下一輪拿走，正是該留下的時候。
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
}
