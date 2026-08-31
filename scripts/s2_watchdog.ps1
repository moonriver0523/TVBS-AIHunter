#Requires -Version 7
<#
.SYNOPSIS
  S2 看門狗——固定排程沒開起來就代打，開關預設關閉。

.DESCRIPTION
  只做一件事：**判斷「這一輪本來該開始，卻完全沒開始」，若是，代打一次**。

  「沒開始」的判準是**log 檔存不存在**——s2_scan.ps1 一啟動就會建 log 檔
  （`掃帶log-{checkpoint}.txt`），所以「log 檔不存在」＝那一輪連叫都沒被叫到
  （0808 19:50 的登入階段錯誤就是這種）。

  **「開始了但中途死掉」（0808 20:10 那種）2026-08-17 起也顧了**（MASTER A5），
  但那段**只推播、不代打**（自動代打是 D5，未裁決），判準也完全不同——
  不能用「log 檔在不在」，那會把成功的慢輪次誤判成卡住。細節見下方 A5 區塊。

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
    # 大檔 stream-json 留本機（跟 s2_scan.ps1 的 -LogDir 一致）
    [string]$LogDir = 'D:\Downloads\S2掃帶log',
    # 小檔遙測放雲端（2026-08-12，跟 s2_scan.ps1 的 -TelemetryDir 一致）
    [string]$WatchdogLog = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log\_看門狗紀錄.txt',

    # ── A5 中途死亡偵測用（2026-08-17）。跟 s2_scan.ps1 的 -TelemetryDir 一致 ──
    [string]$RunsLog = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log\_輪次紀錄.txt',
    [string]$MetricsFile = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log\_token_metrics.jsonl',

    # 排程時刻表——跟 S2掃帶.xml 的 StartBoundary 要保持一致，改排程記得同步改這裡。
    # 2026-08-12 省 token：12 輪 → 9 輪（07:00+08:00 併成 07:30，取消 13:00、23:00）。
    # ⚠️ 這裡沒同步改的話，看門狗會在已取消的時段判定「這輪沒開」而去代打，
    #    等於把取消的輪次又跑回來。
    [string[]]$Slots = @('04:30','07:30','10:00','12:00','17:00','20:00','22:00'),

    # 過了幾分鐘還沒開始才算「沒開」
    [int]$GraceMinutes = 30,

    # 超過這個分鐘數就不追了（下一輪都快到了，追上去只會跟下一輪搶）
    [int]$MaxLatenessMinutes = 90,

    # 代打時要不要帶 TestMode。**必須跟主排程保持一致**，否則代打那一輪會用錯模式。
    # 2026-08-09 起主排程已轉正式（窗內三站全收錄），所以排程呼叫本支時**不傳**這個旗標。
    [switch]$TestMode,
    [int]$TestLimit = 5,

    # A5 判活用：跟 s2_scan.ps1 的 -LockFile 一致。只用 Test-Path 看它在不在，
    # **絕不開檔**（開檔會搶到獨佔握把，害正要啟動的一輪 SKIP）。
    [string]$LockFile = "$env:USERPROFILE\.s2-scan.lock",
    # A5 判活用：那一輪的 掃帶log 幾分鐘沒長就不算「還在寫」
    [int]$LogIdleMinutes = 10,

    # A5：START 後超過這麼久還沒有 DONE／CRASH 才懷疑中途死亡。
    # ⚠️ 不要調低：歷史最久的一輪是 0811-0430 的 56.7 分，正常慢輪不能被當成死掉。
    [int]$DeadRoundMinutes = 75,
    # A5 關掉（只跑原本的代打判斷）
    [switch]$NoDeadCheck,
    # A5 只印判斷結果不推播、不代打，也不需要旗標檔——給驗收與歷史 replay 用
    [switch]$DeadCheckDryRun
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

# G: 沒掛載就把紀錄退回本機，不要讓看門狗變成啞巴
try { New-Item -ItemType Directory -Force -Path (Split-Path $WatchdogLog) -ErrorAction Stop | Out-Null }
catch {
    Write-Warning "看門狗紀錄目錄不可用，改寫本機：$($_.Exception.Message)"
    $WatchdogLog = Join-Path $LogDir '_看門狗紀錄.txt'
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

# 🔴 寫紀錄不准弄死看門狗（2026-08-12）：全域是 -ErrorAction Stop，
# 而紀錄檔已改放 Google Drive，同步鎖檔會讓 Add-Content 丟終止性錯誤。
# 少一行紀錄無所謂，看門狗掛掉才嚴重。
function Write-Log([string]$msg) {
    for ($i = 1; $i -le 3; $i++) {
        try {
            "$stamp`t$msg" | Add-Content -Path $WatchdogLog -Encoding UTF8 -ErrorAction Stop
            return
        } catch {
            if ($i -eq 3) { Write-Warning "看門狗寫紀錄失敗（不影響判斷）：$($_.Exception.Message)"; return }
            Start-Sleep -Milliseconds (300 * $i)
        }
    }
}

if (-not (Test-Path $FlagFile) -and -not $DeadCheckDryRun) {
    # 關閉狀態：完全靜默，連紀錄都不留（否則每 10 分鐘一行變成雜訊）
    # ⚠️ 連 A5 中途死亡偵測也一起關掉——旗標關閉＝這台機器現在不歸看門狗管。
    exit 0
}

$now = Get-Date

# ══ A5：中途死亡偵測（2026-08-17）══════════════════════════════════
# 本支上半部只管「這輪連叫都沒被叫到」（log 檔不存在）。**開始了卻死在半路**
# 是檔案頭註解裡明講「之後若要處理再另外設計」的那件事，這段就是它。
# 🔴 **只推播，不代打**——自動代打是 MASTER D5，尚未裁決，不准在這裡偷跑。
#
# 誤報比漏報更傷（會把警告訓練成雜訊），所以四個條件全中才吵人：
#   1. `_輪次紀錄.txt` 有該 checkpoint 的 START、卻沒有 DONE／CRASH；
#   2. 距 START 已超過 $DeadRoundMinutes；
#   3. 判活的三個訊號都說「沒在跑」（鎖檔不在、那一輪的 log 沒在長、
#      沒有 -File 形式的 s2_scan.ps1 行程）——細節見 Test-ScanRunning；
#   4. `_token_metrics.jsonl` 也沒有那一輪的紀錄。量測寫在 DONE **之後**，
#      所以量測有紀錄＝外殼確實跑到最後，只是 DONE 那行沒落地
#      （Write-Run 遇 Google Drive 鎖檔重試三次會放棄，成功的一輪也可能沒 DONE）。
#
# ⛔ 判活**絕對不准去開鎖檔**：s2_scan.ps1 用 FileShare::None 獨佔，就算只開唯讀
#    握把，在那個瞬間正要啟動的一輪也會拿不到鎖而 SKIP——為了偵測異常反而製造異常。
#    只准 Test-Path 看它在不在（純 metadata，不開檔）。

function Get-UnfinishedRound {
    param([string]$Path, [datetime]$Now, [int]$MinMinutes)

    if (-not (Test-Path $Path)) { return $null }
    # 讀不到（Drive 正在鎖檔）就這輪不判，10 分鐘後看門狗還會再來
    try { $lines = Get-Content -LiteralPath $Path -Encoding UTF8 -ErrorAction Stop }
    catch { return $null }

    $starts = @{}
    $ended = @{}
    foreach ($line in $lines) {
        $f = $line -split "`t"
        # 紀錄檔裡真的有裸的 `000` 這種雜訊行（2026-08-14），欄位不足一律略過
        if ($f.Count -lt 3) { continue }
        $cp = $f[1].Trim()
        # `0811-1800-補漏` 這種後綴要認得，所以不錨結尾
        if ($cp -notmatch '^\d{4}-\d{4}') { continue }
        $kind = $f[2].Trim()
        if ($kind -eq 'START') {
            $t = [datetime]::MinValue
            if ([datetime]::TryParseExact($f[0].Trim(), 'yyyy-MM-dd HH:mm:ss',
                    [Globalization.CultureInfo]::InvariantCulture,
                    [Globalization.DateTimeStyles]::None, [ref]$t)) {
                $starts[$cp] = $t      # 同 checkpoint 重跑過就取最後一次
            }
        } elseif ($kind -like 'DONE*' -or $kind -eq 'CRASH') {
            # `DONE（事後補記）` 也算收工，所以用前綴比對
            $t = [datetime]::MinValue
            if ([datetime]::TryParseExact($f[0].Trim(), 'yyyy-MM-dd HH:mm:ss',
                    [Globalization.CultureInfo]::InvariantCulture,
                    [Globalization.DateTimeStyles]::None, [ref]$t)) {
                $ended[$cp] = $t
            }
        }
    }

    # ⚠️ 比的是**時間先後**，不是「有沒有出現過 DONE」。同一個 checkpoint 被重跑
    #    （前一次收工、這一次死掉）時，只看有無 DONE 會把後面那次的死亡吃掉。
    $cands = foreach ($cp in $starts.Keys) {
        if ($ended.ContainsKey($cp) -and $ended[$cp] -ge $starts[$cp]) { continue }
        $age = ($Now - $starts[$cp]).TotalMinutes
        if ($age -lt $MinMinutes) { continue }
        # 超過一天的舊帳不追：啟用首日不要把歷史翻出來吵一輪
        if ($age -gt 1440) { continue }
        [pscustomobject]@{
            Checkpoint = $cp
            Start      = $starts[$cp]
            AgeMinutes = [Math]::Round($age, 1)
        }
    }
    # 回傳**全部**候選（新到舊）。只回最新一筆的話，同一天死兩輪時，
    # 舊的那一輪會永遠被新的擋在前面、而新的已經警報過＝舊的永不出聲。
    $cands | Sort-Object Start -Descending
}

function Test-ScanRunning {
    <#
      三個獨立訊號，**任何一個說「還活著」就當作還活著**（寧可漏報，
      也不要對正在跑的輪次發假警報）。全部都是唯讀，都不碰鎖檔握把。
    #>
    param([string]$Checkpoint, [datetime]$Start)

    # 1) 鎖檔。Test-Path／Get-Item 只看檔案系統 metadata，**不會開檔**，
    #    所以不會搶到 s2_scan.ps1 的 FileShare::None 獨佔握把。
    #
    # 🔴 **不可以「鎖檔在＝還活著」就了事**——那會讓 A5 在最該作用的情境下失效：
    #    s2_scan.ps1 是在 finally 裡刪鎖檔的，**被硬砍就不會走到 finally**
    #    （排程的 ExecutionTimeLimit 是 PT1H，0811-0430 跑了 56.7 分已經很接近；
    #    0811-2200 的 LastResult=0x8007042B 正是逾時終止碼）。於是死掉的那一輪
    #    留下自己的鎖檔，反而把針對它的警報壓掉，要等下一輪跑起來才會被清掉。
    #
    #    判別方式不必開檔：鎖檔內容只在取得時寫一次，所以 LastWriteTime ≈ 那一輪的
    #    START。**比 START 新**＝是後來的輪次握著（真的有人在跑）；
    #    **不比 START 新**＝這就是死掉那一輪自己的殘檔，不算活著。
    if (Test-Path $LockFile) {
        try {
            $lockTime = (Get-Item -LiteralPath $LockFile -ErrorAction Stop).LastWriteTime
        } catch {
            return $true      # 看不出來就當作有人在跑（寧可漏報）
        }
        if (-not $Start -or $lockTime -gt $Start) { return $true }
    }

    # 2) 那一輪自己的 log 還在長。最精準的訊號：認的是**這個 checkpoint**，
    #    不是「有沒有人在跑什麼」。
    if ($Checkpoint) {
        $lg = Join-Path $LogDir "掃帶log-$Checkpoint.txt"
        if (Test-Path $lg) {
            $idle = ((Get-Date) - (Get-Item $lg).LastWriteTime).TotalMinutes
            if ($idle -lt $LogIdleMinutes) { return $true }
        }
    }

    # 3) 行程命令列。查不到（CIM 壞掉／權限不足）一律當作「有在跑」。
    # ⚠️ 只認 `-File …s2_scan.ps1` 這種**直接啟動**的形式，並排除帶 `-Command`
    #    的處理程序：排程與代打都是用 -File 叫起來的（見 S2掃帶 工作定義與
    #    下方 $scanArgs），而 `-Command` 那種多半是別人（人、agent、CI）在指令
    #    字串裡「提到」這個檔名而已。2026-08-17 實測踩到：一個命令列裡含
    #    s2_scan.ps1 字樣的互動 shell，讓整個中途死亡警報靜音。
    try {
        $procs = Get-CimInstance Win32_Process `
            -Filter "Name='pwsh.exe' OR Name='powershell.exe'" -ErrorAction Stop
    } catch { return $true }
    foreach ($p in $procs) {
        $cl = $p.CommandLine
        if (-not $cl) { continue }
        if ($cl -match '(?i)-Command') { continue }
        if ($cl -match '(?i)-File\s+"?[^"]*s2_scan\.ps1') { return $true }
    }
    return $false
}

function Test-MetricsRecorded {
    param([string]$Path, [string]$Checkpoint)
    if (-not (Test-Path $Path)) { return $false }
    try { $lines = Get-Content -LiteralPath $Path -Encoding UTF8 -ErrorAction Stop }
    catch { return $false }
    foreach ($ln in $lines) {
        if ($ln -match '"checkpoint"\s*:\s*"([^"]+)"' -and $Matches[1] -eq $Checkpoint) {
            return $true
        }
    }
    return $false
}

function Test-AlreadyAlerted {
    param([string]$Path, [string]$Checkpoint)
    if (-not (Test-Path $Path)) { return $false }
    # 讀不到就當作「已經吵過」——寧可晚 10 分鐘再吵，也不要因為驗不了冪等而連環轟炸
    try { $c = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop }
    catch { return $true }
    return ($c -match [regex]::Escape("中途死亡警報 [$Checkpoint]"))
}

if (-not $NoDeadCheck) {
    $cands = @(Get-UnfinishedRound -Path $RunsLog -Now $now -MinMinutes $DeadRoundMinutes)
    # 已經吵過的先濾掉，再取最新一筆——不然同一天死兩輪時，舊的會永遠被
    # 已警報過的新的擋住而不出聲
    $dead = $cands | Where-Object {
        -not (Test-AlreadyAlerted -Path $WatchdogLog -Checkpoint $_.Checkpoint)
    } | Select-Object -First 1

    if ($DeadCheckDryRun) {
        $show = if ($dead) { $dead } else { $cands | Select-Object -First 1 }
        if (-not $show) {
            Write-Host "DeadCheck：沒有可疑輪次（門檻 $DeadRoundMinutes 分）"
        } else {
            Write-Host ("DeadCheck：checkpoint=$($show.Checkpoint) " +
                        "start=$($show.Start.ToString('yyyy-MM-dd HH:mm:ss')) " +
                        "age=$($show.AgeMinutes)分 " +
                        "候選數=$($cands.Count) " +
                        "掃帶行程在跑=$(Test-ScanRunning -Checkpoint $show.Checkpoint -Start $show.Start) " +
                        "有量測紀錄=$(Test-MetricsRecorded -Path $MetricsFile -Checkpoint $show.Checkpoint) " +
                        "已警報過=$(Test-AlreadyAlerted -Path $WatchdogLog -Checkpoint $show.Checkpoint)")
        }
        exit 0
    }
    if ($dead -and
        -not (Test-ScanRunning -Checkpoint $dead.Checkpoint -Start $dead.Start) -and
        -not (Test-MetricsRecorded -Path $MetricsFile -Checkpoint $dead.Checkpoint)) {

        $body = "[$($dead.Checkpoint)] 在 $($dead.Start.ToString('HH:mm')) START，" +
                "已 $($dead.AgeMinutes) 分鐘沒有 DONE／CRASH，且目前沒有掃帶行程在跑、" +
                "也沒有量測紀錄。`n研判該輪中途死亡。看門狗**不代打**，" +
                "請人工確認狀態檔與頂層 checkpoint 要不要補。"
        $err = $null
        try {
            . "$Repo\scripts\s2_notify.ps1"
            $err = Send-Ntfy -Body $body -Title "S2 中途死亡？$($dead.Checkpoint)" `
                             -Tags 'skull' -Priority 'high'
        } catch { $err = $_.Exception.Message }

        # 留痕就是冪等的依據，所以推播成敗都要寫——推播掛了也不能每 10 分鐘重吵
        Write-Log ("中途死亡警報 [$($dead.Checkpoint)]（START 後 $($dead.AgeMinutes) 分" +
                   "無 DONE／CRASH，無掃帶行程、無量測紀錄）" +
                   $(if ($err) { "；推播失敗：$err" } else { '' }))
    }
}
# ══ A5 結束 ══════════════════════════════════════════════════════

# 算出涵蓋「昨天最早時刻 ～ 明天最晚時刻」的所有排程時刻（照 $Slots），取 <= now 裡最近的一個
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

& pwsh -WindowStyle Hidden @scanArgs
$code = $LASTEXITCODE
Write-Log "接手結束 [$checkpoint] 離開碼=$code"
exit $code
