#Requires -Version 7
<#
  登入態推播決策的迴歸（2026-08-09）。

  這段是**無人值守時唯一會叫醒使用者的東西**，而且兩個方向的代價都很痛：
    - 該推沒推 → 一整晚白掃（0808 AP 掉線一小時無人知曉）
    - 不該推卻推 → 半夜被假警報吵醒，**下次就不會再信這個通知了**

  用法：pwsh -File test_s2_notify.ps1
#>
. "$PSScriptRoot\s2_notify.ps1"

$ok = $true
function Report([string]$name, [bool]$passed, [string]$detail = '') {
    $script:ok = $script:ok -and $passed
    Write-Host ("[{0}] {1}{2}" -f $(if ($passed) { 'PASS' } else { 'FAIL' }), $name,
                $(if ($detail) { " — $detail" } else { '' }))
}

# 把一連串狀態餵進去，回傳（累積推播, 最終記憶）
function Feed([string[]]$sequence, [string]$site = 'AP') {
    $prev = @{}
    $all = @()
    foreach ($s in $sequence) {
        $r = Get-NotifyActions -Now @{ $site = $s } -Prev $prev
        $all += $r.Pushes
        $prev = $r.Next
    }
    return @{ Pushes = $all; State = $prev[$site] }
}

# ── 1. 單次 LOGGED_OUT 不推（偽陽性防線）────────────────────────────
$r = Feed @('LOGGED_OUT')
Report "單次 LOGGED_OUT 不推播（0808 02:20 的假警報形狀）" ($r.Pushes.Count -eq 0) "推了 $($r.Pushes.Count) 則"

# ── 2. 掉一次又好了 → 全程零推播 ────────────────────────────────────
$r = Feed @('LOGGED_OUT', 'OK')
Report "掉一次隨即恢復 → 完全不吵人" ($r.Pushes.Count -eq 0) "推了 $($r.Pushes.Count) 則"

# ── 3. 連續兩次 → 推一則警報 ────────────────────────────────────────
$r = Feed @('LOGGED_OUT', 'LOGGED_OUT')
Report "連續兩次 LOGGED_OUT → 推一則" ($r.Pushes.Count -eq 1) "推了 $($r.Pushes.Count) 則"
Report "警報是高優先度" ($r.Pushes.Count -eq 1 -and $r.Pushes[0].Priority -eq 'high')
Report "警報內容指名站別" ($r.Pushes.Count -eq 1 -and $r.Pushes[0].Body -match 'AP')

# ── 4. ⭐ 最關鍵：持續掉線不重複推 ──────────────────────────────────
$r = Feed (1..12 | ForEach-Object { 'LOGGED_OUT' })
Report "連續掉 12 次（等於掉線 6 小時）仍然只推 1 則" ($r.Pushes.Count -eq 1) `
       "推了 $($r.Pushes.Count) 則——>1 就是會把人洗到不信任通知"

# ── 5. 恢復時推一則，且回到乾淨狀態 ─────────────────────────────────
$r = Feed @('LOGGED_OUT', 'LOGGED_OUT', 'OK')
Report "恢復後推一則復原通知（共 2 則）" ($r.Pushes.Count -eq 2) "推了 $($r.Pushes.Count) 則"
Report "恢復後 notified 清乾淨（下次掉線才推得出來）" `
       ($r.State.notified -eq $false -and $r.State.streak -eq 0) `
       "streak=$($r.State.streak) notified=$($r.State.notified)"

# ── 6. 掉→復原→再掉，第二輪要能再推（不可永久沉默）────────────────
$r = Feed @('LOGGED_OUT', 'LOGGED_OUT', 'OK', 'LOGGED_OUT', 'LOGGED_OUT')
Report "第二次掉線能再推（警報1+復原1+警報1=3）" ($r.Pushes.Count -eq 3) "推了 $($r.Pushes.Count) 則"

# ── 7. ERR 既不計數也不清零 ─────────────────────────────────────────
$r = Feed @('LOGGED_OUT', 'ERR')
Report "ERR 不會把 streak 清零（不然永遠湊不滿兩次）" ($r.State.streak -eq 1) "streak=$($r.State.streak)"
$r = Feed @('LOGGED_OUT', 'ERR', 'LOGGED_OUT')
Report "ERR 夾在中間仍能湊滿兩次並推播" ($r.Pushes.Count -eq 1) "推了 $($r.Pushes.Count) 則"
$r = Feed @('ERR', 'ERR', 'ERR', 'ERR')
Report "只有 ERR 不會推播（連不上不等於登出）" ($r.Pushes.Count -eq 0) "推了 $($r.Pushes.Count) 則"

# ── 8. 三站各自獨立計算，互不干擾 ───────────────────────────────────
$prev = @{}
$r1 = Get-NotifyActions -Now @{ NS = 'OK'; AP = 'LOGGED_OUT'; RT = 'OK' } -Prev $prev
$r2 = Get-NotifyActions -Now @{ NS = 'OK'; AP = 'LOGGED_OUT'; RT = 'OK' } -Prev $r1.Next
Report "只有掉線的那一站被推播，另外兩站安靜" `
       ($r2.Pushes.Count -eq 1 -and $r2.Pushes[0].Body -match 'AP') "推了 $($r2.Pushes.Count) 則"
Report "沒掉線的站 streak 保持 0" ($r2.Next['NS'].streak -eq 0 -and $r2.Next['RT'].streak -eq 0)

# ── 9. 全新開機（沒有記憶檔）不應該炸 ───────────────────────────────
$r = Get-NotifyActions -Now @{ AP = 'OK' } -Prev @{}
Report "沒有前次記憶時正常運作、不推播" ($r.Pushes.Count -eq 0)

Write-Host ''
Write-Host $(if ($ok) { '全部通過' } else { '有失敗' })
exit $(if ($ok) { 0 } else { 1 })
