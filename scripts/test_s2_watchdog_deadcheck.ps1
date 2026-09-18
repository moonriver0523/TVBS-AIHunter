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
    param([string]$Title, [string]$LogPath, [string]$ExpectPattern,
          [string]$MetricsPath = 'Z:\no-such-metrics.jsonl',
          [string]$LockPath = 'Z:\no-such.lock')
    $out = & pwsh -NoProfile -File $WD -DeadCheckDryRun `
        -RunsLog $LogPath -MetricsFile $MetricsPath -LockFile $LockPath `
        -LogDir (Join-Path $tmp 'logdir') `
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

# ══ 判活三訊號 ════════════════════════════════════════════════════
$runsDead = New-RunsLog 'live' @("$(T 100)`t0898-2200`tSTART`tmodel=sonnet")

# ── Q1. 鎖檔比 START 新＝後來的輪次握著 → 判成還在跑 ──
$fakeLock = Join-Path $tmp 'fake.lock'
Set-Content -LiteralPath $fakeLock -Value 'pid=1' -Encoding UTF8
(Get-Item $fakeLock).LastWriteTime = (Get-Date).AddMinutes(-30)   # START 是 100 分鐘前
Run-Case 'Q1 鎖檔比START新（後續輪次握著）要判成還在跑' $runsDead '掃帶行程在跑=True' 'Z:\no-such-metrics.jsonl' $fakeLock

# ── Q2. 鎖檔跟 START 同期＝死掉那一輪自己的殘檔 → **不可**壓住警報 ──
# s2_scan.ps1 在 finally 刪鎖檔，被硬砍（ExecutionTimeLimit PT1H 逾時終止，
# 0811-2200 的 0x8007042B 就是）不會走到 finally，殘檔會留下來。
# 「鎖檔在就算活著」會讓 A5 在最該作用的情境下失效。
(Get-Item $fakeLock).LastWriteTime = (Get-Date).AddMinutes(-101)
Run-Case 'Q2 鎖檔是死掉那輪自己的殘檔，不可壓住警報' $runsDead '掃帶行程在跑=False' 'Z:\no-such-metrics.jsonl' $fakeLock
Remove-Item $fakeLock -Force

# ── R. 那一輪的 掃帶log 剛剛還在長 → 不可警報 ──
$logDir = Join-Path $tmp 'logdir'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Content -LiteralPath (Join-Path $logDir '掃帶log-0898-2200.txt') -Value 'x' -Encoding UTF8
Run-Case 'R 該輪 log 還在長要判成還在跑' $runsDead '掃帶行程在跑=True'
Remove-Item (Join-Path $logDir '掃帶log-0898-2200.txt') -Force

# ── S. 只是「命令列裡提到 s2_scan.ps1」的 -Command 行程，不算在跑 ──
# 2026-08-17 實測踩到：一個命令列含該檔名的互動 shell 讓整個警報靜音。
$decoy = Start-Process pwsh -PassThru -WindowStyle Hidden -ArgumentList @(
    '-NoProfile', '-Command',
    "'E:\GitHub\TVBS-AIHunter\scripts\s2_scan.ps1 這只是字串'; Start-Sleep -Seconds 25")
Start-Sleep -Seconds 2
Run-Case 'S -Command 行程只是提到檔名，不算在跑' $runsDead '掃帶行程在跑=False'
Stop-Process -Id $decoy.Id -Force -ErrorAction SilentlyContinue

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
    & pwsh -NoProfile -Command "`$env:USERPROFILE='$home2'; & '$WD' -FlagFile '$flag' -RunsLog '$runs2' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wd2' -Slots '00:01' -LockFile 'Z:\no-such.lock' -LogDir '$tmp'" 2>&1 | Out-Null
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

# ── N2. 同一天死兩輪：舊的那輪不可被「已警報過的新輪」永久擋住 ──
$runs3 = New-RunsLog 'two_dead' @(
    "$(T 200)`t0899-1800`tSTART`tmodel=sonnet"
    "$(T 100)`t0899-2200`tSTART`tmodel=sonnet"
)
$wd5 = Join-Path $tmp 'wd_two.txt'
Remove-Item $wd5 -ErrorAction SilentlyContinue
foreach ($i in 1..2) {
    & pwsh -NoProfile -Command "`$env:USERPROFILE='$home2'; & '$WD' -FlagFile '$flag' -RunsLog '$runs3' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wd5' -Slots '00:01' -LockFile 'Z:\no-such.lock' -LogDir '$tmp'" 2>&1 | Out-Null
}
$two = @(Get-Content -LiteralPath $wd5 -ErrorAction SilentlyContinue)
$hit2200 = @($two | Where-Object { $_ -match '\[0899-2200\]' }).Count
$hit1800 = @($two | Where-Object { $_ -match '\[0899-1800\]' }).Count
"{0}  N2 同日死兩輪各警報一次（2200=$hit2200 1800=$hit1800）" -f `
    $(if ($hit2200 -eq 1 -and $hit1800 -eq 1) { 'PASS' } else { 'FAIL' })

# ── O. 旗標關閉時連 A5 都不動作 ──
Remove-Item $flag -Force
$wd3 = Join-Path $tmp 'wd_off.txt'
Remove-Item $wd3 -ErrorAction SilentlyContinue
& pwsh -NoProfile -Command "`$env:USERPROFILE='$home2'; & '$WD' -FlagFile '$flag' -RunsLog '$runs2' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wd3' -Slots '00:01' -LockFile 'Z:\no-such.lock' -LogDir '$tmp'" 2>&1 | Out-Null
$o = Test-Path $wd3
"{0}  O 旗標關閉時完全靜默" -f $(if (-not $o) { 'PASS' } else { 'FAIL' })

# ── P. -NoDeadCheck 可關掉 A5 ──
Set-Content -LiteralPath $flag -Value '' -Encoding UTF8
$wd4 = Join-Path $tmp 'wd_nodc.txt'
Remove-Item $wd4 -ErrorAction SilentlyContinue
& pwsh -NoProfile -Command "`$env:USERPROFILE='$home2'; & '$WD' -FlagFile '$flag' -RunsLog '$runs2' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wd4' -Slots '00:01' -LockFile 'Z:\no-such.lock' -LogDir '$tmp' -NoDeadCheck" 2>&1 | Out-Null
$pOk = -not (Test-Path $wd4) -or -not (Select-String -Path $wd4 -Pattern '中途死亡' -Quiet)
"{0}  P -NoDeadCheck 可關掉 A5" -f $(if ($pOk) { 'PASS' } else { 'FAIL' })
# ══ schema v2 + supervisor extras ════════════════════════════════════
$ridA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
$ridB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
$ridC = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
function V2([int]$Ago, [string]$Cp, [string]$Rid, [string]$Ev, [string]$Detail = '') {
    "$(T $Ago)`t$Cp`t$Rid`t$Ev`t`t$Detail"
}
function New-LockJson {
    param([int]$PidVal, [string]$Cp, [string]$Rid, [string]$StartedAt)
    $p = Join-Path $tmp "v2-$Rid-$PidVal.lock"
    $obj = @{ schema_version = 2; pid = $PidVal; checkpoint = $Cp; run_id = $Rid; started_at = $StartedAt }
    $json = ($obj | ConvertTo-Json -Compress) + "`n"
    [IO.File]::WriteAllBytes($p, [Text.UTF8Encoding]::new($false).GetBytes($json))
    return $p
}
function IsoFromProcess([datetime]$t) {
    return ([datetimeoffset]$t).ToString('yyyy-MM-ddTHH:mm:sszzz')
}

# V6-1 兩輪同 checkpoint：A 的 DONE 不能關 B
Run-Case 'V6-1 A的DONE不能關B' (New-RunsLog 'v2_ab' @(
    (V2 200 '0918-1300' $ridA 'START' 'model=sonnet')
    (V2 180 '0918-1300' $ridA 'DONE' '離開碼=0')
    (V2 100 '0918-1300' $ridB 'START' 'model=sonnet')
)) 'run_id=bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

# V6-2 DONE_BACKFILL 關同 tuple
Run-Case 'V6-2 DONE_BACKFILL關同tuple' (New-RunsLog 'v2_bf' @(
    (V2 120 '0918-1400' $ridA 'START')
    (V2 90 '0918-1400' $ridA 'DONE_BACKFILL' 'reason=補記')
)) '沒有可疑輪次'

# V6-3 ABORT 關同 tuple
Run-Case 'V6-3 ABORT關同tuple' (New-RunsLog 'v2_abrt' @(
    (V2 120 '0918-1500' $ridA 'START')
    (V2 118 '0918-1500' $ridA 'ABORT' 'headless')
)) '沒有可疑輪次'

# V6-4 CRASH 關同 tuple
Run-Case 'V6-4 CRASH關同tuple' (New-RunsLog 'v2_cr' @(
    (V2 120 '0918-1600' $ridA 'START')
    (V2 110 '0918-1600' $ridA 'CRASH' 'boom')
)) '沒有可疑輪次'

# V6-5 v1 DONE 不能關 v2 START
Run-Case 'V6-5 v1 DONE不能關v2' (New-RunsLog 'v2_v1mix' @(
    "$(T 120)`t0918-1700`tSTART`tmodel=sonnet"
    "$(T 110)`t0918-1700`tDONE`t離開碼=0"
    (V2 100 '0918-1700' $ridA 'START')
)) 'run_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

# V6-6 未完成 v2 START 要抓到
Run-Case 'V6-6 未完成v2 START要抓到' (New-RunsLog 'v2_open' @(
    (V2 100 '0918-1800' $ridC 'START')
)) 'run_id=cccccccc-cccc-4ccc-8ccc-cccccccccccc'

# SKIP/DIAG/NEWDAY 不關
Run-Case 'V2-SKIP不關' (New-RunsLog 'v2_skip' @(
    (V2 120 '0918-1900' $ridA 'START')
    (V2 110 '0918-1900' $ridA 'SKIP' '撞鎖')
)) 'run_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
Run-Case 'V2-DIAG不關' (New-RunsLog 'v2_diag' @(
    (V2 120 '0918-1910' $ridA 'START')
    (V2 110 '0918-1910' $ridA 'DIAG' 'code=METRICS_WRITE_FAILED x')
)) 'run_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
Run-Case 'V2-NEWDAY不關' (New-RunsLog 'v2_nd' @(
    (V2 120 '0918-1920' $ridA 'START')
    (V2 110 '0918-1920' $ridA 'NEWDAY' '建檔')
)) 'run_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

# 未知 v2 event 不得落入 legacy
Run-Case 'V2-未知event忽略不落入legacy' (New-RunsLog 'v2_unk' @(
    (V2 120 '0918-1930' $ridA 'START')
    (V2 110 '0918-1930' $ridA 'WAT' '??')
)) 'run_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

# 量測/警報 de-dup 不可壓另一個 run
$mp2 = Join-Path $tmp 'metrics_v2.jsonl'
Set-Content -LiteralPath $mp2 -Encoding UTF8 -Value '{"schema_version": 2, "checkpoint": "0918-2000", "run_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}'
Run-Case 'V2-量測A不可壓B' (New-RunsLog 'v2_mx' @(
    (V2 100 '0918-2000' $ridB 'START')
)) '有量測紀錄=False' $mp2

$wdDup = Join-Path $tmp 'wd_dup.txt'
Set-Content -LiteralPath $wdDup -Encoding UTF8 -Value "2026-09-18 00:00:00`t中途死亡警報 [0918-2100/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa]"
$runsDup = New-RunsLog 'v2_al' @((V2 100 '0918-2100' $ridB 'START'))
$outDup = & pwsh -NoProfile -File $WD -DeadCheckDryRun -RunsLog $runsDup -MetricsFile 'Z:\nope.jsonl' -LockFile 'Z:\no.lock' -LogDir (Join-Path $tmp 'logdir') -WatchdogLog $wdDup 2>&1 | Out-String
$okDup = $outDup -match '已警報過=False' -and $outDup -match 'run_id=bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
"{0}  V2-警報A不可壓B" -f $(if ($okDup) { 'PASS' } else { 'FAIL' })
if (-not $okDup) { "      輸出：$($outDup.Trim())" }

# ── v2 lock 判活 ──
$me = Get-Process -Id $PID
$isoNow = IsoFromProcess $me.StartTime
$runsLock = New-RunsLog 'v2_lock' @((V2 100 '0918-2200' $ridA 'START'))
$aliveLock = New-LockJson -PidVal $PID -Cp '0918-2200' -Rid $ridA -StartedAt $isoNow
Run-Case 'V2-lock PID+tuple+窗內判活' $runsLock '掃帶行程在跑=True' 'Z:\no-metrics.jsonl' $aliveLock

$missLock = New-LockJson -PidVal 9999999 -Cp '0918-2200' -Rid $ridA -StartedAt $isoNow
Run-Case 'V2-PID missing 不判活' $runsLock '掃帶行程在跑=False' 'Z:\no-metrics.jsonl' $missLock

$np = $null
try {
    $wrongCands = @()
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd -and $pyCmd.Source) { $wrongCands += $pyCmd.Source }
    $wrongCands += "$env:SystemRoot\System32\cmd.exe"
    $wrongExe = $wrongCands | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $wrongExe) { throw '找不到非 pwsh 的測試行程' }
    $wrongArgs = if ($wrongExe -match 'cmd\.exe$') { @('/c', 'timeout', '/t', '40', '/nobreak') } else { @('-c', 'import time; time.sleep(40)') }
    $np = Start-Process -FilePath $wrongExe -ArgumentList $wrongArgs -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 400
    $npIso = IsoFromProcess $np.StartTime
    $wrongLock = New-LockJson -PidVal $np.Id -Cp '0918-2200' -Rid $ridA -StartedAt $npIso
    Run-Case 'V2-錯誤行程名不判活' $runsLock '掃帶行程在跑=False' 'Z:\no-metrics.jsonl' $wrongLock
} catch {
    "FAIL  V2-錯誤行程名不判活 — $($_.Exception.Message)"
} finally {
    if ($np) { Stop-Process -Id $np.Id -Force -ErrorAction SilentlyContinue }
}

$noAt = Join-Path $tmp 'noat.lock'
[IO.File]::WriteAllBytes($noAt, [Text.UTF8Encoding]::new($false).GetBytes((@{schema_version=2;pid=$PID;checkpoint='0918-2200';run_id=$ridA} | ConvertTo-Json -Compress) + "`n"))
Run-Case 'V2-started_at缺失不判活' $runsLock '掃帶行程在跑=False' 'Z:\no-metrics.jsonl' $noAt

$badAt = New-LockJson -PidVal $PID -Cp '0918-2200' -Rid $ridA -StartedAt 'not-a-date'
Run-Case 'V2-started_at壞值不判活' $runsLock '掃帶行程在跑=False' 'Z:\no-metrics.jsonl' $badAt

# StartTime 讀不到：用 lock 指向一個存在但 StartTime 可能為空的系統行程；找不到就略過
$stSkip = $true
foreach ($candPid in @(0, 4)) {
    try {
        $sp = Get-Process -Id $candPid -ErrorAction Stop
        $null = $sp.StartTime
    } catch {
        if ($sp) {
            $stLock = New-LockJson -PidVal $candPid -Cp '0918-2200' -Rid $ridA -StartedAt $isoNow
            Run-Case 'V2-StartTime不可讀不判活' $runsLock '掃帶行程在跑=False' 'Z:\no-metrics.jsonl' $stLock
            $stSkip = $false
            break
        }
    }
}
if ($stSkip) { "SKIP  V2-StartTime不可讀（本機找不到可重現行程）" }

# 容差窗：StartTime ∈ [started_at-5min, started_at+15s]
$insideMinus = ([datetimeoffset]$me.StartTime).AddMinutes(4)
$inLock = New-LockJson -PidVal $PID -Cp '0918-2200' -Rid $ridA -StartedAt ($insideMinus.ToString('yyyy-MM-ddTHH:mm:sszzz'))
Run-Case 'V2-窗內-5min判活' $runsLock '掃帶行程在跑=True' 'Z:\no-metrics.jsonl' $inLock

$outsideMinus = ([datetimeoffset]$me.StartTime).AddMinutes(6)
$outLock = New-LockJson -PidVal $PID -Cp '0918-2200' -Rid $ridA -StartedAt ($outsideMinus.ToString('yyyy-MM-ddTHH:mm:sszzz'))
Run-Case 'V2-窗外-5min不判活' $runsLock '掃帶行程在跑=False' 'Z:\no-metrics.jsonl' $outLock

$insidePlus = ([datetimeoffset]$me.StartTime).AddSeconds(-10)
$inP = New-LockJson -PidVal $PID -Cp '0918-2200' -Rid $ridA -StartedAt ($insidePlus.ToString('yyyy-MM-ddTHH:mm:sszzz'))
Run-Case 'V2-窗內+15s判活' $runsLock '掃帶行程在跑=True' 'Z:\no-metrics.jsonl' $inP

$outsidePlus = ([datetimeoffset]$me.StartTime).AddSeconds(-20)
$outP = New-LockJson -PidVal $PID -Cp '0918-2200' -Rid $ridA -StartedAt ($outsidePlus.ToString('yyyy-MM-ddTHH:mm:sszzz'))
Run-Case 'V2-窗外+15s不判活' $runsLock '掃帶行程在跑=False' 'Z:\no-metrics.jsonl' $outP

# 精確 v2 log 成長（不得靠舊檔名）
$v2logDir = Join-Path $tmp 'logdir'
New-Item -ItemType Directory -Force -Path $v2logDir | Out-Null
Set-Content -LiteralPath (Join-Path $v2logDir "掃帶log-0918-2200-$ridA.txt") -Value 'x' -Encoding UTF8
Run-Case 'V2-精確run log成長判活' $runsLock '掃帶行程在跑=True'
Remove-Item (Join-Path $v2logDir "掃帶log-0918-2200-$ridA.txt") -Force -ErrorAction SilentlyContinue
Set-Content -LiteralPath (Join-Path $v2logDir '掃帶log-0918-2200.txt') -Value 'legacy' -Encoding UTF8
Run-Case 'V2-舊checkpoint log不可替v2判活' $runsLock '掃帶行程在跑=False'
Remove-Item (Join-Path $v2logDir '掃帶log-0918-2200.txt') -Force -ErrorAction SilentlyContinue

# ── 排程「從未開始／代打」：已有 v2 log 或 v2 START 不得當沒跑再代打 ──
$home3 = Join-Path $tmp 'fakehome2'
New-Item -ItemType Directory -Force -Path $home3 | Out-Null
$flag3 = Join-Path $home3 '.s2-watchdog-enabled'
Set-Content -LiteralPath $flag3 -Value '' -Encoding UTF8
$fakeRepo = Join-Path $tmp 'fakerepo'
New-Item -ItemType Directory -Force -Path (Join-Path $fakeRepo 'scripts') | Out-Null
$slot = (Get-Date).AddMinutes(-40)
$slotHHmm = $slot.ToString('HH:mm')
$slotCp = $slot.ToString('MMdd-HHmm')
$schedLogDir = Join-Path $tmp 'schedlog'
New-Item -ItemType Directory -Force -Path $schedLogDir | Out-Null
Set-Content -LiteralPath (Join-Path $schedLogDir "掃帶log-$slotCp-$ridA.txt") -Value 'started' -Encoding UTF8
$wdSched = Join-Path $tmp 'wd_sched.txt'
Remove-Item $wdSched -ErrorAction SilentlyContinue
$runsEmpty = New-RunsLog 'sched_empty' @()
& pwsh -NoProfile -Command "`$env:USERPROFILE='$home3'; & '$WD' -FlagFile '$flag3' -RunsLog '$runsEmpty' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wdSched' -Slots '$slotHHmm' -GraceMinutes 1 -MaxLatenessMinutes 90 -LockFile 'Z:\no.lock' -LogDir '$schedLogDir' -Repo '$fakeRepo' -NoDeadCheck" 2>&1 | Out-Null
$hitSched = (Test-Path $wdSched) -and (Select-String -Path $wdSched -Pattern '接手' -Quiet)
"{0}  V2-排程已有run-log不得代打" -f $(if (-not $hitSched) { 'PASS' } else { 'FAIL' })
if ($hitSched) { Get-Content $wdSched | ForEach-Object { "      $_" } }

$wdSched2 = Join-Path $tmp 'wd_sched2.txt'
Remove-Item $wdSched2 -ErrorAction SilentlyContinue
$schedLogDir2 = Join-Path $tmp 'schedlog2'
New-Item -ItemType Directory -Force -Path $schedLogDir2 | Out-Null
$runsStart = New-RunsLog 'sched_start' @((V2 40 $slotCp $ridA 'START'), (V2 10 $slotCp $ridA 'DONE' '離開碼=0'))
& pwsh -NoProfile -Command "`$env:USERPROFILE='$home3'; & '$WD' -FlagFile '$flag3' -RunsLog '$runsStart' -MetricsFile 'Z:\nope.jsonl' -WatchdogLog '$wdSched2' -Slots '$slotHHmm' -GraceMinutes 1 -MaxLatenessMinutes 90 -LockFile 'Z:\no.lock' -LogDir '$schedLogDir2' -Repo '$fakeRepo' -NoDeadCheck" 2>&1 | Out-Null
$hitSched2 = (Test-Path $wdSched2) -and (Select-String -Path $wdSched2 -Pattern '接手' -Quiet)
"{0}  V2-排程已有v2 START不得把收工輪當沒跑" -f $(if (-not $hitSched2) { 'PASS' } else { 'FAIL' })
if ($hitSched2) { Get-Content $wdSched2 | ForEach-Object { "      $_" } }
