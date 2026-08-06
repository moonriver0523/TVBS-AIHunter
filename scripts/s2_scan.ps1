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

    [string]$Model = 'opus',

    # 開工 prompt 範本；{CHECKPOINT} 會被代換掉。
    [string]$PromptFile = "$PSScriptRoot\s2_scan_prompt.md",

    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [string]$StateDir = 'G:\我的雲端硬碟\Claude共用\自動掃帶系統',
    [string]$LogDir = 'D:\Downloads\S2掃帶log',

    # 鎖檔放本機，不要放 Google Drive——同步延遲會讓互斥失效。
    [string]$LockFile = "$env:USERPROFILE\.s2-scan.lock",

    # 只驗流程不真的叫 claude（排程設定完先用這個試一次）。
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if (-not $Checkpoint) { $Checkpoint = Get-Date -Format 'MMdd-HHmm' }
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$runLog = Join-Path $LogDir "掃帶log-$Checkpoint.txt"
$skipLog = Join-Path $LogDir '_跳過紀錄.txt'

function Write-Skip([string]$why) {
    # ⚠️ 跳過一定要留痕。0806 的教訓：只在終端機講一句等於沒發生過，
    # 而排程根本沒有終端機可看。
    "$stamp`t$Checkpoint`t$why" | Add-Content -Path $skipLog -Encoding UTF8
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
        --add-dir $Repo --add-dir $StateDir `
        --output-format stream-json --verbose *> $runLog
    $code = $LASTEXITCODE
    $mins = [Math]::Round(((Get-Date) - $t0).TotalMinutes, 1)

    # 離開碼 0 不代表掃帶做完了——一定要看產物（0806 就是這樣驗的）
    $mmdd = $Checkpoint.Split('-')[0]
    $stateOk = Test-Path (Join-Path $StateDir "$mmdd-s2-state.json")
    $txtOk = Test-Path (Join-Path $StateDir "$mmdd`晚班交接.txt")

    Write-Host "DONE [$Checkpoint] 離開碼=$code 耗時=${mins}分 state=$stateOk txt=$txtOk"
    if ($code -ne 0 -or -not $stateOk -or -not $txtOk) {
        "$stamp`t$Checkpoint`t異常：離開碼=$code state=$stateOk txt=$txtOk 見 $runLog" |
            Add-Content -Path $skipLog -Encoding UTF8
    }
    exit $code
}
finally {
    if ($lock) { $lock.Dispose() }   # 正常結束、丟例外、Ctrl+C 都會走到這裡
}
