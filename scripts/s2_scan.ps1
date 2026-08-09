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

    # 開工 prompt 範本；{CHECKPOINT} 會被代換掉。
    [string]$PromptFile = "$PSScriptRoot\s2_scan_prompt.md",

    # ⚠️ browser MCP server 只註冊在 .claude.json 的 local scope 'C:/Users/User'，
    # 排程的 cwd 不是那裡就**整組工具都載不到**（0807 22:00 輪三站全 0 則的根因）。
    # 用 --mcp-config 明講，就不再看 cwd 臉色。
    [string]$McpConfig = "$PSScriptRoot\s2_mcp.json",

    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [string]$StateDir = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統',
    [string]$LogDir = 'D:\Downloads\S2掃帶log',

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
$skipLog = Join-Path $LogDir '_跳過紀錄.txt'
# 每一輪的開工／收工都寫這裡（2026-08-09）。在此之前**只有異常才留痕**，
# 成功的 DONE 只印在主控台視窗上——0808 加了 -WindowStyle Hidden 之後那個視窗
# 不再出現，等於「跑完沒有、收了幾則」完全無從得知。**成功也要留痕**，
# 而且要能一眼看完一整天，所以是單一檔案逐行 append，不是每輪一個檔。
$runsLog = Join-Path $LogDir '_輪次紀錄.txt'

function Write-Run([string]$line) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`t$Checkpoint`t$line" |
        Add-Content -Path $runsLog -Encoding UTF8
}

function Write-Skip([string]$why) {
    # ⚠️ 跳過一定要留痕。0806 的教訓：只在終端機講一句等於沒發生過，
    # 而排程根本沒有終端機可看。
    "$stamp`t$Checkpoint`t$why" | Add-Content -Path $skipLog -Encoding UTF8
    Write-Run "SKIP`t$why"
    Write-Host "SKIP [$Checkpoint] $why"
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

    Write-Run "START`tmodel=$Model$(if ($TestMode) { " TestMode(上限$TestLimit)" })"
    Write-Host "START [$Checkpoint] model=$Model log=$runLog"
    if ($DryRun) {
        Write-Host "--- DryRun：以下是會送出的 prompt 前 400 字 ---"
        Write-Host $prompt.Substring(0, [Math]::Min(400, $prompt.Length))
        exit 0
    }

    $t0 = Get-Date
    claude -p $prompt `
        --permission-mode bypassPermissions `
        --model $Model `
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
    if ($bad) {
        "$stamp`t$Checkpoint`t異常：$($bad -join '；') 見 $runLog" |
            Add-Content -Path $skipLog -Encoding UTF8
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
