# 一次性還原腳本：把 S2掃帶 的第 6 個觸發器（索引 5）從 00:30 改回 01:00，然後刪掉自己的排程。
#
# 為什麼要有這支：2026-08-11 使用者下令「0100 那輪提前到 00:30」，做法是直接改
# 每日觸發器的 StartBoundary——那是**永久性**的，不改回來的話往後每天都變 00:30。
# 跟 s2_reenable_2300.ps1 同一個道理：異動的當下就把還原排進去，不要靠人記得。
$ErrorActionPreference = 'Stop'
$log = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log\_跳過紀錄.txt'  # 2026-08-12 遙測搬雲端
try {
    $tr = (Get-ScheduledTask -TaskName 'S2掃帶').Triggers
    $tr[5].StartBoundary = '2026-08-06T01:00:00'
    Set-ScheduledTask -TaskName 'S2掃帶' -Trigger $tr | Out-Null
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "$stamp`t-`t觸發器已自動還原 00:30 → 01:00（單次提前結束）" | Add-Content -Path $log -Encoding UTF8
} catch {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "$stamp`t-`t⚠️ 觸發器還原 01:00 失敗：$($_.Exception.Message)" | Add-Content -Path $log -Encoding UTF8
}
Unregister-ScheduledTask -TaskName 'S2掃帶-還原0100觸發' -Confirm:$false
