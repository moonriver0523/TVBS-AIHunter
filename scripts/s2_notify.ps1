#Requires -Version 7
<#
.SYNOPSIS
  登入態變化 → 該不該推播的**純決策函式**（沒有任何 IO，好測）。

.DESCRIPTION
  拆出來的理由（2026-08-09）：這段邏輯是**無人值守時唯一會叫醒使用者的東西**，
  判斷錯的代價很不對稱——
    - 該推沒推 → 一整晚白掃（0808 AP 掉線一小時無人知曉就是這樣）
    - 不該推卻推 → 半夜被假警報吵醒，**下次就不會再信這個通知了**

  原本跟 IO 混在 s2_keepalive.ps1 裡，只能等真的掉線才驗證得到。
  拆成純函式之後 `test_s2_notify.ps1` 可以把各種序列跑一遍。

  兩條核心規則：
  1. **只在狀態改變時推**——保活每 30 分鐘一次，掉線期間每次都推，一晚會炸出十幾則
     內容一模一樣的通知。**重複通知會把警告訓練成雜訊，那比不通知還糟。**
  2. **連續兩次確認才推**——AP 的判準（頁面有沒有 "Latest"）會偽陽性，
     0808 02:20 報過 LOGGED_OUT、02:50 自己就好了。憑證效期以小時計，
     晚 30 分鐘通知無妨，但假警報只要來一次，這個通知就廢了。

  `ERR`（連不上／逾時）**不計數也不清零**：它既不能證明登出、也不能證明還在。
#>

function Send-Ntfy {
    <#
    .SYNOPSIS
      往 ntfy 頻道送一則推播。**送不出去絕不可以讓呼叫端掛掉。**

    .DESCRIPTION
      從 s2_keepalive.ps1 抽出來共用（2026-08-09）——掃帶收工也要推播，
      兩邊各寫一份遲早會分岔。

      ⛔ **通知永遠比不上它在報告的那件事重要**：保活續期、掃帶收工都不能因為
      推不出去就失敗。所以整段包在 try 裡，失敗只回傳訊息給呼叫端自己記 log。

      頻道名放 `%USERPROFILE%\.s2-ntfy-topic`（**等同密碼，不進版控**）；
      檔案不存在＝沒設定，直接跳過、不報錯。

    .OUTPUTS
      $null＝送出成功或未設定；字串＝失敗原因（呼叫端自行決定要不要記）。
    #>
    param(
        [Parameter(Mandatory)][string]$Body,
        [string]$Title = 'S2',
        [string]$Tags = '',
        [string]$Priority = 'default',
        [string]$TopicFile = "$env:USERPROFILE\.s2-ntfy-topic"
    )
    if (-not (Test-Path $TopicFile)) { return $null }
    $topic = (Get-Content $TopicFile -Raw -ErrorAction SilentlyContinue).Trim()
    if (-not $topic) { return $null }
    try {
        # ⚠️ HTTP 標頭只吃 ASCII，中文一律放 body（body 是 UTF-8，沒問題）
        # ⚠️ 2026-08-12：這台機器的 .NET（Invoke-RestMethod／HttpClient）以主機名稱連
        #    ntfy.sh 必逾時、走 IP 卻正常；curl.exe 完全沒事。故改用 Windows 內建 curl.exe。
        #    body 走暫存檔（--data-binary @file），避免換行與引號在命令列上出事。
        $tmp = [IO.Path]::GetTempFileName()
        [IO.File]::WriteAllBytes($tmp, [Text.Encoding]::UTF8.GetBytes($Body))
        try {
            $curlArgs = @(
                '-sS', '--max-time', '20', '-X', 'POST'
                '--data-binary', "@$tmp"
                '-H', "Title: $Title"
                '-H', "Priority: $Priority"
                '-o', 'NUL', '-w', '%{http_code}'
                "https://ntfy.sh/$topic"
            )
            if ($Tags) { $curlArgs = @('-H', "Tags: $Tags") + $curlArgs }
            $httpCode = & curl.exe @curlArgs 2>&1 | Out-String
            $httpCode = $httpCode.Trim()
            if ($LASTEXITCODE -ne 0) { return "curl 離開碼 $LASTEXITCODE：$httpCode" }
            if ($httpCode -notmatch '^2\d\d$') { return "HTTP $httpCode" }
            return $null
        } finally {
            Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        }
    } catch {
        return $_.Exception.Message
    }
}


function Get-NotifyActions {
    <#
    .PARAMETER Now   @{ NS='OK'; AP='LOGGED_OUT'; RT='ERR' }
    .PARAMETER Prev  上一次的記憶 @{ AP=@{streak=1; notified=$false} }
    .OUTPUTS @{ Next=<新記憶>; Pushes=@(@{Body;Title;Tags;Priority;Log}) }
    #>
    param([hashtable]$Now, [hashtable]$Prev = @{})

    $next = @{}
    $pushes = @()

    foreach ($site in ($Now.Keys | Sort-Object)) {
        $st = $Now[$site]
        $p = $Prev[$site]
        $streak = if ($p -and $p.ContainsKey('streak')) { [int]$p.streak } else { 0 }
        $notified = if ($p -and $p.ContainsKey('notified')) { [bool]$p.notified } else { $false }

        switch ($st) {
            'OK' {
                if ($notified) {
                    $pushes += @{
                        Body = "$site 登入態已恢復，掃帶回復正常。"
                        Title = 'S2 recovered'; Tags = 'white_check_mark'; Priority = 'default'
                        Log = "推播：$site 已恢復"
                    }
                }
                $streak = 0; $notified = $false
            }
            'LOGGED_OUT' {
                $streak++
                if ($streak -ge 2 -and -not $notified) {
                    $pushes += @{
                        Body = ("$site 登入態已失效，需要人工重新登入。`n" +
                                "在此之前 $site 這一站會收 0 則，其餘兩站照跑。")
                        Title = 'S2 login expired'; Tags = 'rotating_light'; Priority = 'high'
                        Log = "推播：$site 需要重新登入（連續 $streak 次）"
                    }
                    $notified = $true
                }
            }
            # ERR：維持原樣，streak／notified 都不動
        }
        $next[$site] = @{ streak = $streak; notified = $notified; last = $st }
    }
    return @{ Next = $next; Pushes = $pushes }
}


# `_skip` 是登入態記憶檔裡的保留鍵，跟站別（NS／AP／RT）並排放。
# 底線開頭是刻意的——一眼看得出它不是站名，也不會跟未來新增的站撞名。
$script:SKIP_KEY = '_skip'

function Get-SkipActions {
    <#
    .SYNOPSIS
      「保活這次跳過了沒」→ 該不該推播的**純決策函式**（同樣沒有 IO）。

    .DESCRIPTION
      2026-08-09 立案、2026-08-10 實作。背景：`.s2-scan.lock` 只有掃帶與保活會拿，
      **人／agent 手動用瀏覽器不會拿**，於是保活會啟第二個 chromium 去搶同一個
      persistent profile，讀不到登入態就誤判成 `LOGGED_OUT`——0809 22:20／22:50
      連推兩則假警報，而當下兩站都活著（NS token 還有 3591 秒、RT 導向 /all）。

      修法是讓保活自己認得「profile 正被別人佔用」並回報 SKIP。但**SKIP 換來的
      風險是靜默失敗**：萬一有個 chromium 沒關乾淨卡在那裡，保活就永遠跳過、
      token 到期沒人續、也沒有任何通知——**那比假警報更糟，因為完全沒有聲音**。
      所以連續跳過到一定次數就要推播。

      ⚠️ **SKIP 既不算成功也不算失敗**：`Get-NotifyActions` 完全不會被呼叫，
      各站的 `streak`／`notified` 一律不動。SKIP 沒有觀察到登入態，
      不該拿它去推翻或佐證上一次的觀察。

    .PARAMETER Skipped   這次是不是跳過了
    .PARAMETER Prev      上一次的完整記憶（含各站與 `_skip`）
    .PARAMETER Threshold 連續跳過幾次才推播。預設 4＝保活每 30 分一次 ⇒ 約 2 小時。
                         NS 的 token 效期 1 小時，2 小時沒續就一定出事了。
    .OUTPUTS @{ Next=<新的 _skip 記憶>; Pushes=@(...) }
    #>
    param([bool]$Skipped, [hashtable]$Prev = @{}, [int]$Threshold = 4)

    $p = $Prev[$script:SKIP_KEY]
    $streak = if ($p -and $p.ContainsKey('streak')) { [int]$p.streak } else { 0 }
    $notified = if ($p -and $p.ContainsKey('notified')) { [bool]$p.notified } else { $false }
    $pushes = @()

    if ($Skipped) {
        $streak++
        if ($streak -ge $Threshold -and -not $notified) {
            $hrs = [math]::Round($streak * 30 / 60, 1)
            $pushes += @{
                Body = ("保活連續 $streak 次被跳過（profile 一直被別的 chromium 佔用）。`n" +
                        "登入態約 $hrs 小時沒有續期，NS 的 token 效期只有 1 小時。`n" +
                        '請確認是不是有瀏覽器沒關乾淨。')
                Title = 'S2 keepalive stuck'; Tags = 'warning'; Priority = 'high'
                Log = "推播：保活被卡住（連續跳過 $streak 次）"
            }
            $notified = $true
        }
    }
    else {
        # 這次真的跑起來了。**只有推播過才回報恢復**——沒吵過人就不必再吵一次。
        if ($notified) {
            $pushes += @{
                Body = '保活已恢復正常執行（profile 不再被佔用）。'
                Title = 'S2 keepalive recovered'; Tags = 'white_check_mark'; Priority = 'default'
                Log = '推播：保活已恢復'
            }
        }
        $streak = 0; $notified = $false
    }
    return @{ Next = @{ streak = $streak; notified = $notified }; Pushes = $pushes }
}
