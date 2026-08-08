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
