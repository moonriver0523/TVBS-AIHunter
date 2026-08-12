#Requires -Version 7
<#
.SYNOPSIS
  S2 定時掃帶啟動器——給 Windows 工作排程器叫的，帶互斥鎖。

.DESCRIPTION
  為什麼要有這支：
  1. **互斥**。Playwright 只有一個 persistent profile，兩輪並行必互鎖
     （0803 空窗八小時、0806 13:00 輪撞到兩次）。實測每輪 16–23 分鐘、
     最短間隔 1 小時，平常有餘裕，但補漏或素材暴增時會撞上。
     這裡用**作業系統層的獨佔檔案握把**當鎖：程序死掉、當機、被 taskkill，
     握把都會被 OS 回收，**不會留下解不開的死鎖**（用「檔案存在與否」當鎖就會）。
  2. **撞到就跳過，不排隊**。上一輪還在跑就記一行 log 然後離開（離開碼 0），
     不等、不硬上。漏掉的輪次事後補掃，比兩輪打架好。
  3. **checkpoint 由這裡算**，不寫死在 prompt 裡。0806 的教訓：指令裡寫死的
     window_start 三小時後就過期了。

  ⚠️ **不做的事**：不殺任何進程。profile 被別人佔著是別人正在用，
  agent 端與這裡都不准 taskkill（見 13b §5 第 4 條）。

.EXAMPLE
  # 手動跑一輪
  pwsh -File E:\GitHub\TVBS-AIHunter\scripts\s2_scan.ps1

.EXAMPLE
  # 工作排程器：程式 pwsh.exe，引數如下
  -NoProfile -File "E:\GitHub\TVBS-AIHunter\scripts\s2_scan.ps1" -Model opus
#>
[CmdletBinding()]
param(
    # 覆寫 checkpoint（預設用現在時間算 {MMDD}-{HHMM}）。補掃時可傳 "0806-1300-補漏"。
    [string]$Checkpoint,

    # 2026-08-09 由 opus 改 sonnet（使用者指定）。改的時候**三個地方要一起改**：
    # 這裡的預設值、工作排程器 `S2掃帶` 的 -Model 引數、`s2_watchdog.ps1` 代打時帶的值。
    # 只改一處會變成「手動跑是 sonnet、排程跑是 opus」這種查半天的不一致。
    [string]$Model = 'sonnet',

    # 2026-08-12 明寫 effort。**不要拿掉改回繼承全域預設**——全域 `effortLevel` 會被
    # 使用者在互動 session 打 `/effort` 順手改掉（0812 就發生過，掃帶其實一直跑在 high
    # 而沒人知道）。
    #
    # ⚠️ **medium 已經試過了，沒效，不要再試一次**：0812 的 0430／0730 兩輪跑 medium，
    # output 不減反增（high 的 0030 輪是 149k，medium 兩輪是 195k／185k）。原因是
    # effort 只縮短「每次思考多深」，但工作量大的輪次思考「次數」變多，直接抵銷掉。
    # 真正的成本變數是**工具呼叫次數**（實測 ≈ 0.47M cache_read/次），不是 effort。
    # 既然 medium 都沒好處，low 只會拿分類品質去換一個沒被證實的節省——**維持 high**。
    [ValidateSet('low', 'medium', 'high')]
    [string]$Effort = 'high',

    # 開工 prompt 範本；{CHECKPOINT} 會被代換掉。
    [string]$PromptFile = "$PSScriptRoot\s2_scan_prompt.md",

    # ⚠️ browser MCP server 只註冊在 .claude.json 的 local scope 'C:/Users/User'，
    # 排程的 cwd 不是那裡就**整組工具都載不到**（0807 22:00 輪三站全 0 則的根因）。
    # 用 --mcp-config 明講，就不再看 cwd 臉色。
    [string]$McpConfig = "$PSScriptRoot\s2_mcp.json",

    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [string]$StateDir = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統',
    # 大檔 stream-json（掃帶log-*.txt，一輪約 1.2MB、整輪持續 append）留本機。
    # ⚠️ **不要搬到 Google Drive**：那是持續串流寫入，Drive 不做差分，
    # 一輪會被反覆整檔重傳幾十次；而且它只是除錯用暫存，分析成本要讀
    # session transcript 而不是這個檔（外殼一死重導向就斷、log 會被截斷）。
    [string]$LogDir = 'D:\Downloads\S2掃帶log',

    # 小檔遙測（_輪次紀錄／_跳過紀錄，合計 <10KB、一輪只 append 幾行）放雲端，
    # 方便跨機查閱與存檔（2026-08-12）。同步壓力等於零。
    # 🔴 寫這裡**一定要走 Write-Run／Write-Skip**——它們有 try/catch，
    #    Drive 鎖檔或 G: 沒掛載時只會警告，不會把整輪弄死。
    [string]$TelemetryDir = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log',

    # 鎖檔放本機，不要放 Google Drive——同步延遲會讓互斥失效。
    [string]$LockFile = "$env:USERPROFILE\.s2-scan.lock",

    # 只驗流程不真的叫 claude（排程設定完先用這個試一次）。
    [switch]$DryRun,

    # 測試模式：真的跑，但**每站只收前 N 則**。驗管線用，不是正式掃帶。
    # ⚠️ 用完記得把排程的 -TestMode 拿掉，否則每輪都只收 5 則還不會報錯。
    [switch]$TestMode,
    [int]$TestLimit = 5
)

$ErrorActionPreference = 'Stop'

if (-not $Checkpoint) { $Checkpoint = Get-Date -Format 'MMdd-HHmm' }
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$runLog = Join-Path $LogDir "掃帶log-$Checkpoint.txt"

# 遙測檔改放雲端（2026-08-12）。建目錄失敗（G: 沒掛載）就整組退回本機 $LogDir，
# **不准讓它中斷掃帶**——這裡是紀錄，不是掃帶本體。
try {
    New-Item -ItemType Directory -Force -Path $TelemetryDir -ErrorAction Stop | Out-Null
} catch {
    Write-Warning "遙測目錄不可用（$TelemetryDir），本輪改寫本機：$($_.Exception.Message)"
    $TelemetryDir = $LogDir
}
$skipLog = Join-Path $TelemetryDir '_跳過紀錄.txt'
# 每一輪的開工／收工都寫這裡（2026-08-09）。在此之前**只有異常才留痕**，
# 成功的 DONE 只印在主控台視窗上——0808 加了 -WindowStyle Hidden 之後那個視窗
# 不再出現，等於「跑完沒有、收了幾則」完全無從得知。**成功也要留痕**，
# 而且要能一眼看完一整天，所以是單一檔案逐行 append，不是每輪一個檔。
$runsLog = Join-Path $TelemetryDir '_輪次紀錄.txt'

# 🔴 **這個函式不准往外丟例外**（2026-08-12 立規）。
# 全域是 $ErrorActionPreference='Stop'，遙測檔又搬到了 Google Drive；
# 只要 Drive 在同步當下鎖住檔案，一個 Add-Content 失敗就會**整輪中斷**。
# 寫 log 失敗只是少一行紀錄，絕對不該比掃帶本身重要。
# 鎖檔是暫時的，所以退避重試三次；三次都不行就印警告收工。
function Write-Line([string]$path, [string]$text) {
    for ($i = 1; $i -le 3; $i++) {
        try {
            $text | Add-Content -Path $path -Encoding UTF8 -ErrorAction Stop
            return
        } catch {
            if ($i -eq 3) {
                Write-Warning "寫紀錄失敗（已重試 3 次，不影響本輪）：$path — $($_.Exception.Message)"
                Write-Warning "遺失的內容：$text"
                return
            }
            Start-Sleep -Milliseconds (300 * $i)
        }
    }
}

function Write-Run([string]$line) {
    Write-Line $runsLog "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`t$Checkpoint`t$line"
}

function Write-Skip([string]$why) {
    # ⚠️ 跳過一定要留痕。0806 的教訓：只在終端機講一句等於沒發生過，
    # 而排程根本沒有終端機可看。
    Write-Line $skipLog "$stamp`t$Checkpoint`t$why"
    Write-Run "SKIP`t$why"
    Write-Host "SKIP [$Checkpoint] $why"
}

function New-ShiftState {
    <#
      建檔輪專用：確保今天這個班次的狀態檔存在，並把上一班歸檔。

      ⚠️ **冪等**：今天的檔已經在就什麼都不做——補跑 16:00、手動重跑都安全。
      ⛔ **不碰素材內容**：只建一個空殼，素材照樣由 agent 掃進來。
      📌 window_start 照 `13b §5a` 第 4 條＝**前一天最後一輪的排定時刻，常態就是 13:00**。
         這是排程設計上的交界點，**不是「昨天實際跑到哪一輪」**——漏跑時照字面算會
         少報好幾小時、還把沒人掃過的空窗算進涵蓋範圍（0808 斷電那次的教訓）。
    #>
    # ⚠️ 班次日期一律從 **checkpoint** 取，不要用 Get-Date：
    #    補跑時會傳 `0810-1600-補漏` 這種值，照系統日期算就會建到錯的那天。
    $mmdd = $Checkpoint.Substring(0, 4)
    $today = Join-Path $StateDir "$mmdd-s2-state.json"
    if (Test-Path $today) {
        Write-Run "NEWDAY`tSKIP 今天的狀態檔已存在，不重建：$mmdd-s2-state.json"
        return
    }

    # 上一班＝資料夾裡現有的、檔名不是今天的那份（正常只會有一份）
    $prev = Get-ChildItem $StateDir -Filter '*-s2-state.json' -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne "$mmdd-s2-state.json" } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1

    $body = [ordered]@{
        window_start  = '{0:yyyy-MM}-{1} 13:00' -f (Get-Date), $mmdd.Substring(2, 2)
        checkpoint    = $Checkpoint
        window_local  = ''
        reconcile_log = @{}
        alerts        = @()          # 🔴 檔頭重大：新的一天從零開始，不沿用昨天
        updated_at    = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        items         = @()
    }
    # ⚠️ PowerShell 的 ConvertTo-Json 對空陣列會吐 null，Python 端會炸；用 -Depth 保住結構
    $json = $body | ConvertTo-Json -Depth 6
    # 空集合被轉成 null 的兩個欄位補回來（實測 items/alerts 會中招）
    $json = $json -replace '"alerts":\s*null', '"alerts": []' -replace '"items":\s*null', '"items": []'
    [System.IO.File]::WriteAllText($today, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Run "NEWDAY`t已建立 $mmdd-s2-state.json（window_start=$($body.window_start)）"
    Write-Host "NEWDAY 已建立 $mmdd-s2-state.json"

    # ── 上一班歸檔：Archive\{YYYYMMDD}\ ────────────────────────────
    if ($prev) {
        $pm = $prev.Name.Substring(0, 4)                       # 0809
        $yyyy = (Get-Date).Year
        # 跨年：12 月底建檔時上一班可能還是去年的（例 0101 輪看到 1231）
        if ($pm -gt $mmdd) { $yyyy-- }
        $dest = Join-Path $StateDir "Archive\$yyyy$pm"
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        $moved = 0
        Get-ChildItem $StateDir -File | Where-Object { $_.Name -like "$pm*" } | ForEach-Object {
            Move-Item $_.FullName -Destination $dest -Force; $moved++
        }

        # ── 當日暫存夾 → Archive\{YYYYMMDD}\_暫存\（2026-08-11 加）────────
        # 🔴 **這裡是「雙包」的根因**：`s2_state.py` 的 `scratch_dir()` 把暫存夾也命名成
        #    `{YYYYMMDD}`，跟這裡的定版歸檔夾**同名同層**。以前是人工把暫存夾搬進
        #    `Archive\`，於是同一層出現兩個 `20260808`——Google Drive 允許同層同名，
        #    Windows 用戶端只好把第二個改名成 `20260808 (1)`。0805～0808 四天全中。
        #    修法不是改名字，是**收成子資料夾**：定版產物在 `{YYYYMMDD}\`，
        #    暫存進 `{YYYYMMDD}\_暫存\`，永遠不會再同名。
        # ⚠️ 用 `-LiteralPath`：資料夾名純數字，但沿用同一套寫法比較不會踩萬用字元。
        $scratch = Join-Path $StateDir "$yyyy$pm"
        if (Test-Path -LiteralPath $scratch) {
            $sDest = Join-Path $dest "_暫存"
            New-Item -ItemType Directory -Force -Path $sDest | Out-Null
            $sN = (Get-ChildItem -LiteralPath $scratch -Recurse -File -EA SilentlyContinue).Count
            Get-ChildItem -LiteralPath $scratch -Force | Move-Item -Destination $sDest -Force
            Remove-Item -LiteralPath $scratch -Recurse -Force
            Write-Run "NEWDAY`t暫存夾 $yyyy$pm 已歸檔 $sN 個檔 → Archive\$yyyy$pm\_暫存"
        }

        # ── `_待整併` 的當日殘檔 → Archive\{YYYYMMDD}\_待整併\（2026-08-11 加）──
        # `_待整併` 是**跨天共用**一個資料夾、靠 `{MMDD}-` 前綴區分，入庫後沒人清，
        # 於是舊交件檔一直堆著；下一輪 agent 看到它們無從判斷「這是今天要整併的，
        # 還是昨天已經入庫的」——0810 就靠人工比對 239 筆才敢刪。
        # 交班時把當日的一起收進母資料夾，`_待整併` 每天自然回到空的。
        # ⚠️ **只搬前綴符合的那天**，不要整夾清空——當下可能已經有今天的新交件。
        $pend = Join-Path $StateDir "_待整併"
        if (Test-Path -LiteralPath $pend) {
            $old = @(Get-ChildItem -LiteralPath $pend -File | Where-Object { $_.Name -like "$pm*" })
            if ($old.Count) {
                $pDest = Join-Path $dest "_待整併"
                New-Item -ItemType Directory -Force -Path $pDest | Out-Null
                $old | ForEach-Object { Move-Item $_.FullName -Destination $pDest -Force }
                Write-Run "NEWDAY`t_待整併 $pm 殘檔已歸檔 $($old.Count) 個 → Archive\$yyyy$pm\_待整併"
            }
        }

        Write-Run "NEWDAY`t上一班 $pm 已歸檔 $moved 個檔 → Archive\$yyyy$pm"
        Write-Host "NEWDAY $pm 已歸檔（$moved 個檔）"
    } else {
        Write-Run "NEWDAY`t⚠️ 找不到上一班的狀態檔，沒有東西可歸檔——第一次啟用才正常"
    }
}

# ── 互斥鎖：獨佔握把，OS 保證釋放 ───────────────────────────────────
$lock = $null
try {
    $lock = [System.IO.File]::Open(
        $LockFile, [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch [System.IO.IOException] {
    Write-Skip '上一輪還在跑（鎖被佔），本輪跳過——不排隊、不硬上'
    exit 0        # ← 排程器看到的是「正常結束」，不是失敗
}

try {
    # 誰拿著鎖、什麼時候拿的（跑到一半當掉時查得出來）
    $w = New-Object System.IO.StreamWriter($lock)
    $w.WriteLine("pid=$PID checkpoint=$Checkpoint started=$stamp")
    $w.Flush()

    # ── 建檔輪：新的一天由**腳本**開檔，不交給 agent 判斷（2026-08-10 訂案）──
    # 🔴 0810-1600 實錯：agent 去開 `0810-s2-state.json` 拿到 FileNotFoundError，
    #    於是**退回昨天那份繼續寫**，再改名輸出成 `0810晚班交接.txt`——
    #    昨天的 398 則全部被當成今天的，而且**全程沒有任何一步報錯**。
    # 📌 根因在 `s2_state.py default_file()`：它回傳「最新修改的那份」，
    #    而建檔輪那一刻最新的必然是昨天。0809 修過的是同一個位置的**反方向**錯誤
    #    （當時寫死一個永遠不存在的路徑，害 agent 把還在用的檔案切成兩份）。
    #    兩次都是靜默失敗——所以這件事不該再靠任何人記得，改由這裡做掉。
    # ⚠️ 用**前綴**比對，不要錨到結尾：16:00 整輪失敗要補跑時傳的是
    #    `0811-1600-補漏`，錨結尾就永遠不會建檔——而那正是最需要它的場合。
    if ($Checkpoint -match '^\d{4}-1600') { New-ShiftState }

    if (-not (Test-Path $PromptFile)) { throw "找不到 prompt 範本：$PromptFile" }
    $prompt = (Get-Content $PromptFile -Raw -Encoding UTF8) -replace '\{CHECKPOINT\}', $Checkpoint

    if ($TestMode) {
        # 擺在最後面，蓋掉範本裡「窗內全部收齊」的預設立場
        $prompt += @"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 本輪是【測試模式】，目的是驗管線通不通，不是正式掃帶。

- **每站最多只收 $TestLimit 則**（挑最新的），收滿就停，其餘一律不收。
- **不要**為了「窗內零漏收」去補掃整段時間窗——本輪本來就不求收齊。
- 清單對帳照跑（那正是要驗的東西之一），但**窗內未收會是一大串，那是預期的**，
  不必處理、也不要據此判定失敗。在 needs-review 記一則說明本輪是測試模式即可。
- 其餘流程（分類、render、稽核、留痕）全部照正常做——**要驗的就是這些**。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"@
        Write-Host "*** TestMode：每站上限 $TestLimit 則 ***"
    }

    # 🔴 DryRun 的出口要在 Write-Run 之前（2026-08-12 修）。
    # 原本順序相反，每跑一次 DryRun 就在 _輪次紀錄.txt 留一行假的 START
    # （後面永遠不會有對應的 DONE），還順手生一個 0 bytes 的 掃帶log-*.txt。
    # 手動清過兩次。驗測試設定時 DryRun 要跑很多次，這條不修就等於紀錄檔報廢。
    if ($DryRun) {
        Write-Host "--- DryRun [$Checkpoint] model=$Model effort=$Effort（不寫 _輪次紀錄）---"
        Write-Host "以下是會送出的 prompt 前 400 字："
        Write-Host $prompt.Substring(0, [Math]::Min(400, $prompt.Length))
        exit 0
    }

    Write-Run "START`tmodel=$Model`teffort=$Effort$(if ($TestMode) { " TestMode(上限$TestLimit)" })"
    Write-Host "START [$Checkpoint] model=$Model effort=$Effort log=$runLog"

    $t0 = Get-Date
    claude -p $prompt `
        --permission-mode bypassPermissions `
        --model $Model `
        --effort $Effort `
        --mcp-config $McpConfig `
        --add-dir $Repo --add-dir $StateDir `
        --output-format stream-json --verbose *> $runLog
    $code = $LASTEXITCODE
    $mins = [Math]::Round(((Get-Date) - $t0).TotalMinutes, 1)

    # ⚠️ 離開碼 0 不代表掃帶做完了。**只檢查「檔案在不在」也不夠**——
    # 0807 22:00 輪三站全部進不去，state 與 txt 照樣被建出來（裡面 0 則）、
    # 離開碼還是 0，檢查全過。**沒有素材的那一輪，看起來跟成功的一輪一模一樣。**
    # 所以這裡要看**本輪實際收了幾則**。
    # ⚠️ **不能用 checkpoint 的 MMDD 去組檔名**（0808-0100 輪實錯）：
    # 晚班交接檔是**跨夜**的，凌晨 01:00 那輪屬於前一天的班次，寫的是
    # `0807-s2-state.json`。拿日曆日 `0808` 去找檔案永遠找不到，
    # 結果是**成功的一輪被誤報成異常**。誤報比漏報更傷——會把警告訓練成雜訊。
    # 改成反過來找：哪一份狀態檔的 checkpoint 等於本輪，那份就是。
    # ⚠️ **不能只認頂層 checkpoint**（0809-0800 實錯）：那一輪收了 13 則、也做了三站對帳，
    # 但 agent **忘了 set-top**，頂層仍停在 `0809-0700`。結果這裡找不到檔案 → 誤報
    # 「本輪 0 則、txt 沒產出」，而實際上東西都在。**誤報比漏報更傷，會把警告訓練成雜訊。**
    # 改成兩條路都認：頂層 checkpoint 相符 **或** 裡面有本輪寫進去的素材。
    # 兩者的差別本身就是有用的訊號——見下方 $topStale。
    $statePath = $null
    $topStale = $false
    foreach ($f in Get-ChildItem $StateDir -Filter '*-s2-state.json' -File |
                   Sort-Object LastWriteTime -Descending) {
        try {
            $j = Get-Content $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            $hasItems = @($j.items | Where-Object { $_.first_seen_checkpoint -eq $Checkpoint }).Count -gt 0
            if ($j.checkpoint -eq $Checkpoint) { $statePath = $f.FullName; $st = $j; break }
            if ($hasItems) {
                # 有本輪的素材、但頂層沒推進＝忘了 set-top
                $statePath = $f.FullName; $st = $j; $topStale = $true; break
            }
        } catch { }
    }
    $added = -1
    $txtOk = $false
    if ($statePath) {
        $mmdd = [System.IO.Path]::GetFileName($statePath).Split('-')[0]
        $txtOk = Test-Path (Join-Path $StateDir "$mmdd`晚班交接.txt")
        # 只算本輪新增的，不是整份總數——否則舊素材會把空輪次蓋過去
        $added = @($st.items | Where-Object { $_.first_seen_checkpoint -eq $Checkpoint }).Count
    }

    Write-Host "DONE [$Checkpoint] 離開碼=$code 耗時=${mins}分 本輪新增=$added 則 txt=$txtOk"
    $bad = @()
    if ($code -ne 0) { $bad += "離開碼=$code" }
    if (-not $txtOk) { $bad += 'txt 沒產出' }
    if ($added -eq 0) { $bad += '本輪 0 則——多半是三站都進不去，不是真的沒素材' }
    if ($added -lt 0) { $bad += "找不到 checkpoint=$Checkpoint 的狀態檔——該輪可能整個沒跑完" }
    # 素材有進來、頂層卻沒推進：東西沒丟，但 render 的對帳查核會去查上一輪的紀錄
    # 而誤放行（0809-0800 實錯）。單獨列一條，不要跟「整輪沒跑」混在一起。
    if ($topStale) {
        $bad += "本輪素材有寫入但**頂層 checkpoint 沒推進**（忘了 set-top）——" +
                "會讓 render 的對帳查核查到上一輪紀錄而誤放行；補跑 " +
                "``s2_state.py set-top checkpoint $Checkpoint``"
    }
    Write-Run ("DONE`t離開碼=$code`t耗時=${mins}分`t本輪新增=$added 則`ttxt=$txtOk" +
               $(if ($bad) { "`t⚠️ $($bad -join '；')" } else { '' }))

    # ── 收工推播（2026-08-09 使用者要求「每一輪掃完也通知」）──────────
    # ⚠️ **一天 12 輪，每輪都讓手機響就會變成新的雜訊**，然後你開始忽略它——
    # 那正是我們今天在誤報上反覆學到的教訓。所以：
    #   正常收工 → `low` 優先度（留在通知列、不出聲）
    #   有異常   → `high` 優先度（該吵你的時候才吵）
    # ⛔ 推播失敗絕不可以影響離開碼——通知永遠比不上它在報告的那件事重要。
    try {
        . "$PSScriptRoot\s2_notify.ps1"
        $srcTxt, $missTxt = '', ''
        if ($statePath) {
            $mine = @($st.items | Where-Object { $_.first_seen_checkpoint -eq $Checkpoint })
            # ⚠️ 外層的 $_ 會被內層 Where-Object 蓋掉，一定要先接成變數
            $srcTxt = (@('NS', 'AP', 'RT') | ForEach-Object {
                $s = $_
                "$s $(@($mine | Where-Object { $_.source -eq $s }).Count)"
            }) -join '／'
            # 對帳的「窗內未收」才是真漏收，值得寫進通知
            $rl = $st.reconcile_log.$Checkpoint
            if ($rl) {
                $miss = @('RT', 'AP', 'NS') | ForEach-Object {
                    $v = $rl.$_
                    if ($v -and $v.missing -gt 0) { "$_ 漏$($v.missing)" }
                }
                $missTxt = if ($miss) { "`n窗內未收：" + ($miss -join '／') } else { "`n窗內零漏收" }
            } else {
                $missTxt = "`n⚠️ 沒有對帳留痕"
            }
        }
        $body = "本輪新增 $added 則（$srcTxt）`n耗時 ${mins} 分$missTxt" +
                $(if ($bad) { "`n⚠️ " + ($bad -join '；') } else { '' })
        $err = Send-Ntfy -Body $body `
            -Title "S2 $Checkpoint" `
            -Tags $(if ($bad) { 'warning' } else { 'white_check_mark' }) `
            -Priority $(if ($bad) { 'high' } else { 'low' })
        if ($err) { Write-Run "推播失敗（不影響本輪）：$err" }
    } catch {
        Write-Run "推播例外（不影響本輪）：$($_.Exception.Message)"
    }
    if ($bad) {
        Write-Line $skipLog "$stamp`t$Checkpoint`t異常：$($bad -join '；') 見 $runLog"
        Write-Host "*** 異常：$($bad -join '；') ***"
    }
    exit $code
}
catch {
    # ⚠️ 沒有這段的話，**外殼自己爆掉那一輪會完全無聲**——0808 20:49 手動測試就是
    # claude 跑完、狀態檔也寫了，但外殼在收工前死掉，事後只能靠比對檔案時間去猜。
    # 視窗藏起來之後更沒有第二個管道，所以例外一定要落檔再往外丟。
    Write-Run "CRASH`t$($_.Exception.Message)"
    throw
}
finally {
    if ($lock) { $lock.Dispose() }   # 正常結束、丟例外、Ctrl+C 都會走到這裡
}
