#Requires -Version 7
<#
.SYNOPSIS
  歐印萬掃帶全自動 autopilot——資料夾有新側錄檔就自動跑 ASR + 派 Grok 寫 TC中文大段翻譯，
  不依賴任何 Claude Code session 存活（走 Grok 訂閱額度 headless 呼叫）。

.DESCRIPTION
  跟 common/15-歐印萬掃帶.md 描述的「監控模式」同一份規則，差別是最後一步從
  「通知 Claude agent 處理」改成「腳本自己呼叫 grok -p headless 處理」，
  所以不需要有人開著 Claude Code session、也不受 CronCreate session-only 限制。

  流程（見 common/15-歐印萬掃帶.md 權威版）：
    1. 開關檢查：$FlagFile 不存在就直接退出（預設關閉，跟 s2_watchdog 同慣例）。
    2. 互斥鎖：避免排程重疊時撞車（跟 s2_scan.ps1 同慣例）。
    3. git pull + 重新讀取規則檔——**每輪都讀最新版**，不把規則凍結進本腳本，
       避免 common/15 那段「規則改了排程不知道」的舊坑（2026-08-02 實錯教訓）。
    4. 列出資料夾媒體檔，排除已有輸出檔（_TC中文大段翻譯.txt / _雙語逐字稿.txt）的。
    5. 排除「檔名前綴（記錄人+來源）從未出現過」的新名字——不自動處理，寫進
       待確認清單並跳過，等使用者人工確認格式（比照規則「新人名先問」精神，
       headless 模式沒有人可以即時回答 AskUserQuestion，所以改成排入佇列而非硬猜）。
    6. 檔案改動時間需超過 $StableMinutes 分鐘，避免處理到雲端同步中途的半截檔。
    7. 對每個合格新檔：跑 oyinwan_asr_draft.py 產生原始逐字稿 → 把逐字稿全文
       + common/15 全文規則餵給 grok -p headless → 存成 {檔名}_TC中文大段翻譯.txt。
    8. 寫執行紀錄到 $WatchdogLog。

.EXAMPLE
  # 手動測試一次
  pwsh -NoProfile -File scripts\oyinwan_grok_autopilot.ps1 -DryRun

  # 開機／登入排程（建議每 10-15 分鐘跑一次，Windows工作排程器）：
  # 程式: pwsh.exe
  # 引數: -NoProfile -File "E:\GitHub\TVBS-AIHunter\scripts\oyinwan_grok_autopilot.ps1"

  # 開關：
  #   啟用: New-Item -ItemType File "$env:USERPROFILE\.oyinwan-grok-enabled" -Force
  #   停用: Remove-Item "$env:USERPROFILE\.oyinwan-grok-enabled" -Force
#>
[CmdletBinding()]
param(
    [string]$FlagFile = "$env:USERPROFILE\.oyinwan-grok-enabled",
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [string]$Folder = 'G:\我的雲端硬碟\Autopilot\(掃帶歐印萬) 檔名取TC起頭 6位數',
    [string]$KnownNamesFile = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\_歐印萬已知記錄人.txt',
    [string]$PendingReviewFile = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\_歐印萬待確認新名字.txt',
    [string]$WatchdogLog = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統\_歐印萬Grok自動化紀錄.txt',
    [string]$LockFile = "$env:TEMP\.oyinwan-grok-autopilot.lock",
    [int]$StableMinutes = 3,
    [string]$GrokModel = '',
    [string]$CodexFallbackModel = 'gpt-5.6-luna',
    [string]$CodexFallbackEffort = 'xhigh',
    [switch]$DryRun
)

[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Write-Log([string]$msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Output $line
    try {
        $dir = Split-Path -Parent $WatchdogLog
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Add-Content -LiteralPath $WatchdogLog -Value $line -Encoding utf8
    } catch {}
}

# ── 1. 開關 ──
if (-not (Test-Path $FlagFile)) {
    Write-Output "SKIP: flag file not present ($FlagFile) — autopilot disabled"
    exit 0
}

# ── 2. 互斥鎖 ──
if (Test-Path $LockFile) {
    $age = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($age.TotalMinutes -lt 30) {
        Write-Output "SKIP: lock held (age=$([int]$age.TotalMinutes)min) — previous run still active or crashed recently"
        exit 0
    }
}
New-Item -ItemType File -Path $LockFile -Force | Out-Null
try {

    # ── 3. git pull + 重讀規則 ──
    Push-Location $Repo
    try { git pull --ff-only 2>&1 | Out-Null } catch { Write-Log "WARN: git pull failed: $_" }
    Pop-Location
    $rulesPath = Join-Path $Repo 'common\15-歐印萬掃帶.md'
    if (-not (Test-Path $rulesPath)) { Write-Log "ERROR: rules file not found at $rulesPath"; exit 1 }
    $rulesText = Get-Content -LiteralPath $rulesPath -Raw -Encoding utf8

    # ── 4. 列媒體檔，排除已處理 ──
    $mediaFiles = Get-ChildItem -LiteralPath $Folder -Recurse -Include *.wav, *.mxf, *.mp4 -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\Archive\\' }

    function Test-AlreadyProcessed([System.IO.FileInfo]$f) {
        $base = Join-Path $f.DirectoryName ([IO.Path]::GetFileNameWithoutExtension($f.Name))
        (Test-Path "${base}_TC中文大段翻譯.txt") -or (Test-Path "${base}_雙語逐字稿.txt") -or
        (Test-Path "$($f.FullName).txt") -or (Test-Path "$($f.FullName)(雙語對照版).txt")
    }

    $candidates = $mediaFiles | Where-Object {
        -not (Test-AlreadyProcessed $_) -and
        ((Get-Date) - $_.LastWriteTime).TotalMinutes -ge $StableMinutes
    }

    if (-not $candidates) {
        Write-Log "本次監控無新檔案"
        exit 0
    }

    # ── 5. 新記錄人名字檢查：2026-09-16 使用者裁決「開放全部名字，不用列管」，直接放行 ──
    $toProcess = @($candidates)

    if (-not $toProcess) {
        Write-Log "本次監控無新檔案"
        exit 0
    }

    if ($DryRun) {
        Write-Log "DRY RUN，將處理: $($toProcess.Name -join ', ')"
        exit 0
    }

    # ── 7. 逐檔處理 ──
    foreach ($f in $toProcess) {
        Write-Log "開始處理: $($f.FullName)"
        $base = Join-Path $f.DirectoryName ([IO.Path]::GetFileNameWithoutExtension($f.Name))
        $draftPath = "${base}_原始逐字稿.txt"

        if (-not (Test-Path $draftPath)) {
            Push-Location $Repo
            try {
                python scripts\oyinwan_asr_draft.py "$($f.FullName)" 2>&1 | Tee-Object -Variable asrOut | Out-Null
            } finally { Pop-Location }
            if (-not (Test-Path $draftPath)) {
                Write-Log "ERROR: ASR 失敗，跳過 $($f.Name)。輸出: $asrOut"
                continue
            }
        }

        $draftText = Get-Content -LiteralPath $draftPath -Raw -Encoding utf8

        $prompt = @"
你是歐印萬掃帶 pipeline 的「TC中文大段翻譯」產生器。以下是這個任務的權威規則全文（common/15-歐印萬掃帶.md），規則裡「兩種輸出格式」一節只需要「TC中文大段翻譯」這一種（監控模式預設格式，不要輸出雙語逐字稿）：

===== 規則全文開始 =====
$rulesText
===== 規則全文結束 =====

來源檔名：$($f.Name)
以下是這支音檔的原始逐字稿（本機 ASR 產生，含相對時間戳與已加偏移的絕對TC，逐段直接抄絕對TC欄位，不要自己心算）：

===== 原始逐字稿開始 =====
$draftText
===== 原始逐字稿結束 =====

請嚴格依照規則產生「{檔名}_TC中文大段翻譯.txt」的完整內容（檔頭五行 → 150字內重點摘要 → ##### → 逐段TC與內文）。
只輸出檔案最終內容本身，不要任何額外說明、不要 markdown code fence、不要「以下是...」這類前言。
"@

        # --cwd 指到來源檔案所在子資料夾，讓 Grok 能穩定查到「接續前檔」等同資料夾脈絡
        # （2026-09-16 實測：給了 --cwd 才能穩定抓到接續關係，不給時偶爾也會自己探，但不穩定）
        $grokArgs = @('-p', $prompt, '--always-approve', '--disable-web-search', '--cwd', $f.DirectoryName)
        if ($GrokModel) { $grokArgs = @('-m', $GrokModel) + $grokArgs }

        $output = & grok @grokArgs 2>&1
        $outputText = ($output -join "`n").Trim()
        $engine = 'grok'

        # 2026-09-16 新增：Grok 訂閱額度耗盡時（quota/rate limit 類錯誤）改用 Codex 備援
        # （模型 $CodexFallbackModel，reasoning effort=$CodexFallbackEffort，走 ChatGPT 訂閱額度，
        #  不是重試同一個已耗盡的 grok 指令——呼應 project_codex_grok_dual_mode_dispatch 額度用完處理原則）
        if ($outputText -match '(?i)quota|rate.?limit|usage limit|429') {
            Write-Log "WARN: Grok 額度疑似耗盡（輸出含 quota/rate limit 關鍵字），改用 Codex 備援模型 $CodexFallbackModel (effort=$CodexFallbackEffort)：$($f.Name)"
            Push-Location $f.DirectoryName
            try {
                $codexArgs = @('exec', '-m', $CodexFallbackModel, '-c', "model_reasoning_effort=`"$CodexFallbackEffort`"", '--sandbox', 'read-only', $prompt)
                $output = & codex @codexArgs 2>&1
            } finally { Pop-Location }
            $outputText = ($output -join "`n").Trim()
            $engine = 'codex-fallback'
        }

        # 2026-09-16 實測發現：Grok headless 輸出偶爾會在真正檔頭前混入自己的思考/工具使用敘事文字
        # （例如「先對齊寫稿通則、資料夾接續檔與專名查證...」），必須後處理砍掉，只留檔頭起始的真正內容。
        # 判準：檔頭第一行固定格式「{來源} 逐字稿(TC中文大段翻譯)— {檔名}」，取這個 pattern 第一次出現的位置切掉前面雜訊。
        $headerMatch = [regex]::Match($outputText, '(?m)^.*逐字稿\(TC中文大段翻譯\)—.*$')
        if ($headerMatch.Success -and $headerMatch.Index -gt 0) {
            Write-Log "WARN: 輸出前段混入雜訊文字，已自動截掉前 $($headerMatch.Index) 字元 ($($f.Name))"
            $outputText = $outputText.Substring($headerMatch.Index).Trim()
        } elseif (-not $headerMatch.Success) {
            Write-Log "ERROR: Grok 輸出找不到預期檔頭格式，跳過寫檔 $($f.Name)。原始輸出已存供除錯: ${base}_grok原始輸出.debug.txt"
            $outputText | Out-File -LiteralPath "${base}_grok原始輸出.debug.txt" -Encoding utf8
            continue
        }

        if (-not $outputText -or $outputText.Length -lt 50) {
            Write-Log "ERROR: Grok 輸出異常（過短或空白），跳過寫檔 $($f.Name)。原始輸出已存供除錯: ${base}_grok原始輸出.debug.txt"
            $outputText | Out-File -LiteralPath "${base}_grok原始輸出.debug.txt" -Encoding utf8
            continue
        }

        $outPath = "${base}_TC中文大段翻譯.txt"
        $outputText | Out-File -LiteralPath $outPath -Encoding utf8
        Write-Log "完成($engine): $outPath"
    }

} finally {
    Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
}
