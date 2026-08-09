#Requires -Version 7
<#
.SYNOPSIS
  S2 看門狗——固定排程沒開起來就代打，開關預設關閉。

.DESCRIPTION
  只做一件事：**判斷「這一輪本來該開始，卻完全沒開始」，若是，代打一次**。

  「沒開始」的判準是**log 檔存不存在**——s2_scan.ps1 一啟動就會建 log 檔
  （`掃帶log-{checkpoint}.txt`），所以「log 檔不存在」＝那一輪連叫都沒被叫到
  （0808 19:50 的登入階段錯誤就是這種）。**這支不管「開始了但中途死掉」**
  （0808 20:10 那種）——那是另一個問題，用同一招會誤判成功的慢輪次為卡住，
  之後若要處理再另外設計。

  代打時用**原本那一輪該有的 checkpoint**（時刻表算出來的，不是現在時間），
  不然時間窗會對不起來。代打本身就是呼叫 s2_scan.ps1，**互斥鎖天然防雙跑**：
  如果主排程其實有觸發、只是還在跑，鎖是被佔的，代打會自己 SKIP 退出，
  不會跟主排程打架。

  **開關預設關閉**：看門狗排程可以一直存在，但不建旗標檔就什麼都不做。
  開／關用 s2_watchdog_ctl.ps1，不要手動戳這支。

.EXAMPLE
  # 工作排程器：程式 pwsh.exe，引數如下（建議每 10 分鐘跑一次）
  -NoProfile -File "E:\GitHub\TVBS-AIHunter\scripts\s2_watchdog.ps1"
#>
[CmdletBinding()]
param(
    [string]$FlagFile = "$env:USERPROFILE\.s2-watchdog-enabled",
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [string]$LogDir = 'D:\Downloads\S2掃帶log',
    [string]$WatchdogLog = 'D:\Downloads\S2掃帶log\_看門狗紀錄.txt',

    # 排程時刻表——跟 S2掃帶.xml 的 12 個 StartBoundary 要保持一致，改排程記得同步改這裡
    [string[]]$Slots = @('16:00','18:00','20:00','22:00','23:00','01:00','04:30','07:00','08:00','10:00','12:00','13:00'),

    # 過了幾分鐘還沒開始才算「沒開」
    [int]$GraceMinutes = 30,

    # 超過這個分鐘數就不追了（下一輪都快到了，追上去只會跟下一輪搶）
    [int]$MaxLatenessMinutes = 90,

    # 代打時要不要帶 TestMode。**必須跟主排程保持一致**，否則代打那一輪會用錯模式。
    # 2026-08-09 起主排程已轉正式（窗內三站全收錄），所以排程呼叫本支時**不傳**這個旗標。
    [switch]$TestMode,
    [int]$TestLimit = 5
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

function Write-Log([string]$msg) {
    "$stamp`t$msg" | Add-Content -Path $WatchdogLog -Encoding UTF8
}

if (-not (Test-Path $FlagFile)) {
    # 關閉狀態：完全靜默，連紀錄都不留（否則每 10 分鐘一行變成雜訊）
    exit 0
}

$now = Get-Date

# 算出涵蓋「昨天16:00 ～ 明天13:00」的所有排程時刻，取 <= now 裡最近的一個
$candidates = foreach ($base in @($now.Date.AddDays(-1), $now.Date, $now.Date.AddDays(1))) {
    foreach ($t in $Slots) {
        [datetime]::ParseExact("$($base.ToString('yyyy-MM-dd')) $t", 'yyyy-MM-dd HH:mm', $null)
    }
}
$targetSlot = $candidates | Where-Object { $_ -le $now } | Sort-Object -Descending | Select-Object -First 1
if (-not $targetSlot) { Write-Log '算不出最近一個排程時刻，異常，略過'; exit 0 }

$minutesSince = ($now - $targetSlot).TotalMinutes
if ($minutesSince -lt $GraceMinutes) { exit 0 }          # 還沒到代打門檻
if ($minutesSince -gt $MaxLatenessMinutes) { exit 0 }    # 太舊了，不追（避免跟下一輪打架）

$checkpoint = $targetSlot.ToString('MMdd-HHmm')
$expectedLog = Join-Path $LogDir "掃帶log-$checkpoint.txt"

if (Test-Path $expectedLog) {
    # log 檔在＝那一輪主排程有被叫到（不管跑完沒有），不是本支負責的情況
    exit 0
}

Write-Log "接手 [$checkpoint]（該輪已過 $([Math]::Round($minutesSince,1)) 分鐘仍無 log 檔，判定主排程沒開起來）"

$scanArgs = @(
    '-NoProfile', '-File', "$Repo\scripts\s2_scan.ps1",
    '-Checkpoint', $checkpoint,
    '-Model', 'sonnet'      # 跟主排程一致（2026-08-09 由 opus 改）——兩邊不一樣，代打輪就會用錯 model
)
if ($TestMode) { $scanArgs += @('-TestMode', '-TestLimit', $TestLimit) }

& pwsh @scanArgs
$code = $LASTEXITCODE
Write-Log "接手結束 [$checkpoint] 離開碼=$code"
exit $code
