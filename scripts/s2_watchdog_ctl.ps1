#Requires -Version 7
<#
.SYNOPSIS
  S2 看門狗開關——on demand 啟用/停用，不改任何排程設定本身。

.EXAMPLE
  pwsh -File scripts\s2_watchdog_ctl.ps1 -On
.EXAMPLE
  pwsh -File scripts\s2_watchdog_ctl.ps1 -Off
.EXAMPLE
  pwsh -File scripts\s2_watchdog_ctl.ps1 -Status
#>
[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(ParameterSetName = 'On')][switch]$On,
    [Parameter(ParameterSetName = 'Off')][switch]$Off,
    [Parameter(ParameterSetName = 'Status')][switch]$Status,
    [string]$FlagFile = "$env:USERPROFILE\.s2-watchdog-enabled"
)

# ⚠️ 旗標檔與排程任務**兩個都要切**（2026-08-09）。
# 原本只切旗標，排程任務永遠開著——它每 10 分鐘觸發一次（**一天 144 次**），
# 每次都在桌面閃一下主控台視窗，即使當下什麼事都不做。`-WindowStyle Hidden`
# 治不了那個閃爍（排程器啟動 pwsh 時 OS 已先配好視窗）。
# ⛔ **不可以改用 S4U 消除閃爍**（保活是那樣解的）：看門狗代打時會叫 s2_scan.ps1，
#    那支需要**有畫面的**瀏覽器、必須待在互動桌面；session 0 會讓代打整個壞掉。
# 📌 只切一邊會製造最糟的狀態——**回報「已開啟」但排程根本不會執行**，
#    正是 0808 建立當天踩過的坑（`0x80070002`），不要重蹈。
$TaskName = 'S2看門狗'

function Set-Task([bool]$enable) {
    try {
        if ($enable) { Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null }
        else { Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null }
        return $true
    } catch {
        Write-Warning "排程任務『$TaskName』切換失敗：$($_.Exception.Message)"
        return $false
    }
}

if ($On) {
    Set-Content -Path $FlagFile -Value (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') -Encoding UTF8
    $okTask = Set-Task $true
    Write-Host "看門狗已開啟（旗標檔：$FlagFile）"
    if ($okTask) {
        Write-Host "排程任務已啟用——每 10 分鐘檢查一次。"
        Write-Host "⚠️ 開著的期間桌面每 10 分鐘會閃一下主控台視窗，這是預期的；用完記得 -Off。"
    } else {
        Write-Warning "⚠️ 旗標開了但排程任務沒啟用成功——看門狗實際上不會執行，請手動確認。"
    }
} elseif ($Off) {
    if (Test-Path $FlagFile) { Remove-Item $FlagFile -Force }
    Set-Task $false | Out-Null
    Write-Host "看門狗已關閉（旗標與排程任務都已停用，桌面不會再閃）"
} else {
    $state = (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
    if (Test-Path $FlagFile) {
        $since = (Get-Content $FlagFile -Raw).Trim()
        Write-Host "看門狗目前：開啟（自 $since 起）／排程任務：$state"
        if ($state -eq 'Disabled') {
            Write-Warning "⚠️ 旗標是開的但排程任務被停用——看門狗不會執行。重跑一次 -On 修正。"
        }
    } else {
        Write-Host "看門狗目前：關閉／排程任務：$state"
        if ($state -ne 'Disabled') {
            Write-Warning "⚠️ 旗標是關的但排程任務仍啟用——它會每 10 分鐘空跑並閃視窗。重跑一次 -Off 修正。"
        }
    }
}
