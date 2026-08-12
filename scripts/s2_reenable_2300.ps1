# 一次性還原腳本：把 S2掃帶 的 23:00 觸發器（索引 4）重新啟用，然後刪掉自己的排程。
#
# 為什麼要有這支：2026-08-11 使用者下令「先取消 2300 掃帶」，做法是停用單一觸發器。
# 停用容易、**記得還原很難**——忘了就等於 23:00 那輪從此永久消失，而且不會有任何
# 錯誤訊息（跟 0811-1800 那種無聲死法一樣）。所以取消的當下就把還原也排進去。
$ErrorActionPreference = 'Stop'
$log = 'D:\Downloads\S2掃帶log\_跳過紀錄.txt'
try {
    $t  = Get-ScheduledTask -TaskName 'S2掃帶'
    $tr = $t.Triggers
    $tr[4].Enabled = $true
    Set-ScheduledTask -TaskName 'S2掃帶' -Trigger $tr | Out-Null
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "$stamp`t-`t23:00 觸發器已自動還原（單次取消結束）" | Add-Content -Path $log -Encoding UTF8
} catch {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "$stamp`t-`t⚠️ 23:00 觸發器還原失敗：$($_.Exception.Message)" | Add-Content -Path $log -Encoding UTF8
}
Unregister-ScheduledTask -TaskName 'S2掃帶-還原2300觸發' -Confirm:$false
