#Requires -Version 7
# A5 中途死亡偵測 replay 測試（唯讀，只碰 scratchpad 底下的假檔）
$ErrorActionPreference = 'Stop'
$WD = Join-Path $PSScriptRoot 's2_watchdog.ps1'
# 假檔一律落系統暫存夾，不要污染 repo（R13 教訓：暫存檔亂落 repo 根）
$tmp = Join-Path ([IO.Path]::GetTempPath()) 's2_a5_test'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

function New-RunsLog {
    param([string]$Name, [string[]]$Lines)
    $p = Join-Path $tmp "$Name.txt"
    Set-Content -LiteralPath $p -Value $Lines -Encoding UTF8
    return $p
}
function T([int]$MinutesAgo) { (Get-Date).AddMinutes(-$MinutesAgo).ToString('yyyy-MM-dd HH:mm:ss') }

function Run-Case {
    param([string]$Title, [string]$LogPath, [string]$ExpectPattern, [string]$MetricsPath = 'Z:\no-such-metrics.jsonl')
    $out = & pwsh -NoProfile -File $WD -DeadCheckDryRun `
        -RunsLog $LogPath -MetricsFile $MetricsPath `
        -WatchdogLog (Join-Path $tmp 'wd.txt') 2>&1 | Out-String
    $out = $out.Trim()
    $ok = $out -match $ExpectPattern
    "{0}  {1}" -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $Title
    "      輸出：$out"
    if (-not $ok) { "      預期符合：$ExpectPattern" }
}

# ── A. 真實中途死亡（0811-2200 原型：START 後沒有任何收尾行）──
Run-Case 'A 真實中途死亡應被抓到' (New-RunsLog 'a' @(
    "$(T 300)`t0811-2000`tSTART`tmodel=sonnet"
    "$(T 280)`t0811-2000`tDONE`t離開碼=0`t耗時=21分"
    "$(T 100)`t0811-2200`tSTART`tmodel=sonnet"
)) 'checkpoint=0811-2200'

# ── B. 有 DONE 但帶警告（0811-1800 txt=False）→ 必須靜默 ──
Run-Case 'B 有DONE帶警告不該報' (New-RunsLog 'b' @(
    "$(T 100)`t0811-1800`tSTART`tmodel=sonnet"
    "$(T 88)`t0811-1800`tDONE`t離開碼=0`t耗時=11.6分`t本輪新增=-1 則`ttxt=False`t⚠️ txt 沒產出"
)) '沒有可疑輪次'

# ── C. 有 DONE 但離開碼=1（0814-1000）→ 必須靜默 ──
Run-Case 'C 離開碼1仍有DONE不該報' (New-RunsLog 'c' @(
    "$(T 120)`t0814-1000`tSTART`tmodel=sonnet"
    "$(T 80)`t0814-1000`tDONE`t離開碼=1`t耗時=39.4分"
)) '沒有可疑輪次'

# ── D. DONE（事後補記）也算收工（0811-2200 實際那行）──
Run-Case 'D DONE（事後補記）算收工' (New-RunsLog 'd' @(
    "$(T 120)`t0811-2200`tSTART`tmodel=sonnet"
    "$(T 90)`t0811-2200`tDONE（事後補記）`t離開碼=未知`t耗時=29.5分"
)) '沒有可疑輪次'

# ── E. CRASH 也算收尾 ──
Run-Case 'E CRASH算收尾' (New-RunsLog 'e' @(
    "$(T 120)`t0815-1200`tSTART`tmodel=sonnet"
    "$(T 118)`t0815-1200`tCRASH`t某某例外"
)) '沒有可疑輪次'

# ── F. 未達門檻（跑了 40 分，正常慢輪）→ 必須靜默 ──
Run-Case 'F 慢輪未達門檻不該報' (New-RunsLog 'f' @(
    "$(T 40)`t0815-1600`tSTART`tmodel=sonnet"
)) '沒有可疑輪次'

# ── G. 雜訊行（裸 000）不能弄壞解析，且同檔的死亡輪照抓 ──
Run-Case 'G 雜訊行不影響解析' (New-RunsLog 'g' @(
    "$(T 200)`t0814-0730`tSTART`tmodel=sonnet"
    "$(T 180)`t0814-0730`tDONE`t離開碼=0"
    "000"
    ""
    "$(T 100)`t0814-1200`tSTART`tmodel=sonnet"
)) 'checkpoint=0814-1200'

# ── H. 後綴 checkpoint（-補漏）也要認得 ──
Run-Case 'H 補漏輪後綴要認得' (New-RunsLog 'h' @(
    "$(T 100)`t0811-1800-補漏`tSTART`tmodel=sonnet"
)) 'checkpoint=0811-1800-補漏'

# ── I. 超過一天的舊帳不追 ──
Run-Case 'I 隔天以上舊帳不追' (New-RunsLog 'i' @(
    "$(T 3000)`t0815-2200`tSTART`tmodel=sonnet"
)) '沒有可疑輪次'

# ── J. 有量測紀錄＝外殼跑到最後（DONE 只是沒落地）→ 訊號要顯示 True ──
$mp = Join-Path $tmp 'metrics.jsonl'
Set-Content -LiteralPath $mp -Encoding UTF8 -Value '{"checkpoint": "0816-1800", "requests": 10}'
Run-Case 'J 有量測紀錄要被偵測到' (New-RunsLog 'j' @(
    "$(T 100)`t0816-1800`tSTART`tmodel=sonnet"
)) '有量測紀錄=True' $mp

# ── K. 同 checkpoint 重跑：前一次已 DONE、這一次死掉 → 要抓到後面那次 ──
Run-Case 'K 同checkpoint重跑後死亡要抓到' (New-RunsLog 'k' @(
    "$(T 300)`t0816-1600`tSTART`tmodel=sonnet"
    "$(T 280)`t0816-1600`tDONE`t離開碼=0"
    "$(T 100)`t0816-1600`tSTART`tmodel=sonnet"
)) 'checkpoint=0816-1600'

# ── K2. 同 checkpoint 重跑且兩次都收工 → 靜默 ──
Run-Case 'K2 重跑兩次都收工要靜默' (New-RunsLog 'k2' @(
    "$(T 300)`t0816-1600`tSTART`tmodel=sonnet"
    "$(T 280)`t0816-1600`tDONE`t離開碼=0"
    "$(T 100)`t0816-1600`tSTART`tmodel=sonnet"
    "$(T 85)`t0816-1600`tDONE`t離開碼=0"
)) '沒有可疑輪次'

# ── L. 紀錄檔不存在→安靜，不炸 ──
Run-Case 'L 紀錄檔不存在不炸' 'Z:\no-such-runs.txt' '沒有可疑輪次'

# ══ 真實路徑（非 DryRun）：留痕與冪等 ══════════════════════════════
# 把子行程的 USERPROFILE 指到空的暫存家目錄：`.s2-ntfy-topic` 不存在時
# Send-Ntfy 直接回 $null（不送、不報錯），所以能走完整條路徑而**不會真的推播**。
$home2 = Join-Path $tmp 'fakehome'
New-Item -ItemType Directory -Force -Path $home2 | Out-Null
$flag = Join-Path $home2 '.s2-watchdog-enabled'
Set-Content -LiteralPath $flag -Value '' -Encoding UTF8
$wd2 = Join-Path $tmp 'wd_real.txt'
Remove-Item $wd2 -ErrorAction SilentlyContinue
$runs2 = New-RunsLog 'real' @("$(T 100)`t0899-2200`tSTART`tmodel=sonnet")

function Invoke-Real {
    & pwsh -NoProfile -Command "`$env:USERPROFILE='$home2'; & '$WD' -FlagFile '$flag' -RunsLog '$runs2' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wd2' -Slots '00:01'" 2>&1 | Out-Null
}
Invoke-Real
$after1 = @(Get-Content -LiteralPath $wd2 -ErrorAction SilentlyContinue)
$m1 = @($after1 | Where-Object { $_ -match '中途死亡警報 \[0899-2200\]' }).Count
"{0}  M 真實路徑會留痕（找到 $m1 行）" -f $(if ($m1 -eq 1) { 'PASS' } else { 'FAIL' })
$after1 | ForEach-Object { "      $_" }

Invoke-Real
$after2 = @(Get-Content -LiteralPath $wd2 -ErrorAction SilentlyContinue)
$m2 = @($after2 | Where-Object { $_ -match '中途死亡警報 \[0899-2200\]' }).Count
"{0}  N 冪等：第二次不重複警報（仍為 $m2 行）" -f $(if ($m2 -eq 1) { 'PASS' } else { 'FAIL' })

# ── O. 旗標關閉時連 A5 都不動作 ──
Remove-Item $flag -Force
$wd3 = Join-Path $tmp 'wd_off.txt'
Remove-Item $wd3 -ErrorAction SilentlyContinue
& pwsh -NoProfile -Command "`$env:USERPROFILE='$home2'; & '$WD' -FlagFile '$flag' -RunsLog '$runs2' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wd3' -Slots '00:01'" 2>&1 | Out-Null
$o = Test-Path $wd3
"{0}  O 旗標關閉時完全靜默" -f $(if (-not $o) { 'PASS' } else { 'FAIL' })

# ── P. -NoDeadCheck 可關掉 A5 ──
Set-Content -LiteralPath $flag -Value '' -Encoding UTF8
$wd4 = Join-Path $tmp 'wd_nodc.txt'
Remove-Item $wd4 -ErrorAction SilentlyContinue
& pwsh -NoProfile -Command "`$env:USERPROFILE='$home2'; & '$WD' -FlagFile '$flag' -RunsLog '$runs2' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wd4' -Slots '00:01' -NoDeadCheck" 2>&1 | Out-Null
$pOk = -not (Test-Path $wd4) -or -not (Select-String -Path $wd4 -Pattern '中途死亡' -Quiet)
"{0}  P -NoDeadCheck 可關掉 A5" -f $(if ($pOk) { 'PASS' } else { 'FAIL' })
