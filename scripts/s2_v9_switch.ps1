#Requires -Version 7
<#
.SYNOPSIS
  S2 掃帶規則 V8 ⇄ V9 一鍵切換（只換 13c／13c2 兩份執行版）。預設唯讀，只印狀態。

.DESCRIPTION
  2026-09-14 使用者裁示：0914 省 Token 評估 §三 的規則文字異動另存成 V9 平行版，
  不直接覆蓋 V8，出問題可一鍵切回。

  - V9 來源：`common/v9/13c-…md`、`common/v9/13c2-…md`
  - V8 備份：`common/v9/_v8bak/`（分叉當下的 V8 原檔；-On 時再以 live 內容覆寫一次）
  - 分叉基準：`common/v9/FORK-BASE.txt` 記 V8 兩檔的 sha256（行尾先正規化成 LF）。
    -On 前比對：V8 live 自分叉後若被改過，直接切 V9 會把那些修正退掉 → 擋下。

  切換方式＝**原地換掉兩份規則檔內容**，檔名不變，所以 `s2_rules_check.py`、
  `s2_scan.ps1`、`s2_bash_guard.py`、`s2_token_metrics.py` 的八檔清單都不用改。
  規則是每輪開跑時才讀，切換後**下一輪自動生效**，不必重啟排程、看門狗或保活。

  ⚠️ 切到 V9 後主工作樹這兩檔會顯示為已修改（git status）。這是預期狀態；
     要讓 V9 正式成為 main 內容，另行 commit；要回 V8 跑 -Off，不要 git checkout 蓋掉備份流程。
  ⚠️ 腳本改動（§二量測分桶、§四 build lint、§六 rename-field）是新增／選用行為，
     不隨本支切換，回滾靠 git。

.EXAMPLE
  pwsh -File scripts\s2_v9_switch.ps1          # 看狀態（唯讀）
  pwsh -File scripts\s2_v9_switch.ps1 -On      # 切到 V9
  pwsh -File scripts\s2_v9_switch.ps1 -Off     # 退回 V8
#>
[CmdletBinding()]
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Force,                 # 略過「輪次可能在跑」與「V8 漂移」兩道警告
    [string]$Repo = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$names  = @('13c-S2-執行版-上-入口與三站擷取.md', '13c2-S2-執行版-下-狀態檔與指令.md')
$common = Join-Path $Repo 'common'
$v9dir  = Join-Path $common 'v9'
$bakdir = Join-Path $v9dir '_v8bak'
$forkf  = Join-Path $v9dir 'FORK-BASE.txt'
$lock   = "$env:USERPROFILE\.s2-scan.lock"
$check  = Join-Path $Repo 'scripts\s2_rules_check.py'

# 🔴 雜湊前先把行尾正規化成 LF（沿用 v5/v7 switch 的修正：autocrlf 會改位元組雜湊）。
function Sha([string]$p) {
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    $text = [System.IO.File]::ReadAllText($p) -replace "`r`n", "`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }
    finally { $sha.Dispose() }
}

function Get-ForkBase([string]$name) {
    if (-not (Test-Path -LiteralPath $forkf)) { return $null }
    foreach ($line in [System.IO.File]::ReadAllLines($forkf)) {
        $parts = $line -split '\s+'
        if ($parts.Count -ge 2 -and $parts[1] -eq $name) { return $parts[0] }
    }
    return $null
}

# 看檔頭第一行判定版本；兩檔不一致回 MIXED（切一半）。
function Get-FileVersion([string]$p) {
    if (-not (Test-Path -LiteralPath $p)) { return 'MISSING' }
    # ⛔ 不要用 ReadLines | Select -First 1：列舉器沒被釋放會鎖住檔案，接著 Copy-Item 就失敗。
    $sr = [System.IO.StreamReader]::new($p)
    try { $first = $sr.ReadLine() } finally { $sr.Dispose() }
    if ($first -match 'V9（執行版）') { return 'V9' }
    if ($first -match 'V8（執行版）') { return 'V8' }
    return 'UNKNOWN'
}
function Get-LiveVersion {
    $vs = @($names | ForEach-Object { Get-FileVersion (Join-Path $common $_) } | Select-Object -Unique)
    if ($vs.Count -eq 1) { return $vs[0] } else { return 'MIXED' }
}

# ⛔ 只看鎖檔存不存在，絕不開檔（開檔會搶 s2_scan.ps1 的獨佔握把，害該輪 SKIP）。
function Test-Busy {
    if (Test-Path -LiteralPath $lock) { return $true }
    $running = @(Get-CimInstance Win32_Process -Filter "Name='pwsh.exe' OR Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 's2_scan\.ps1' })
    return ($running.Count -gt 0)
}

function Invoke-RulesCheck {
    # 🔴 輸出一定要 Out-Host：否則 python 的 stdout 會混進函式回傳值，
    #    `(Invoke-RulesCheck) -ne 0` 變成拿陣列比對而永遠為真（2026-09-14 實測踩到）。
    # python 叫不起來時不能讓腳本在「已換成 V9」的狀態下中止 → 當成檢查失敗回傳，走自動還原。
    try { & python -X utf8 $check --quiet | Out-Host; return $LASTEXITCODE }
    catch { Write-Host "❌ 無法執行 rules_check：$($_.Exception.Message)" -ForegroundColor Red; return 99 }
}

function Show-Status {
    Write-Host ''
    Write-Host '== S2 規則版本狀態（13c／13c2）==' -ForegroundColor Cyan
    Write-Host "生效中   : $(Get-LiveVersion)"
    foreach ($n in $names) {
        $live = Join-Path $common $n; $src = Join-Path $v9dir $n; $bak = Join-Path $bakdir $n
        Write-Host "  $n"
        Write-Host "    live=$(Get-FileVersion $live)  V9來源=$(if (Test-Path -LiteralPath $src) { 'OK' } else { '❌缺檔' })  V8備份=$(if (Test-Path -LiteralPath $bak) { 'OK' } else { '❌缺檔' })"
        $fork = Get-ForkBase $n
        if ((Get-FileVersion $live) -eq 'V8' -and $fork) {
            if ((Sha $live) -eq $fork) { Write-Host '    V8 漂移：無' -ForegroundColor Green }
            else { Write-Host '    V8 漂移：⚠️ 自 V9 分叉後 V8 已被改過——切換前先把修正補進 common/v9/' -ForegroundColor Yellow }
        }
    }
    Write-Host "掃帶狀態 : $(if (Test-Busy) { '⚠️ 有鎖檔或 s2_scan.ps1 在跑' } else { '空閒' })"
    Write-Host ''
}

if ($On -and $Off) { Write-Host '❌ -On 與 -Off 只能擇一' -ForegroundColor Red; exit 1 }
if (-not $On -and -not $Off) { Show-Status; exit 0 }

# 🔴 函式呼叫要自己括起來（v5 switch 2026-09-01 踩過：否則 -and 會被當成函式引數）。
if ((Test-Busy) -and -not $Force) {
    Write-Host '⚠️ 輪次或保活可能正在跑。建議等跑完再切；確定要照換請加 -Force。' -ForegroundColor Yellow
    exit 1
}

if ($On) {
    $cur = Get-LiveVersion
    if ($cur -eq 'V9') { Write-Host '已經是 V9，不必再切。' -ForegroundColor Green; exit 0 }
    if ($cur -ne 'V8') {
        Write-Host "❌ 目前 live 是 $cur，不是 V8；本支只負責 V8 ⇄ V9。" -ForegroundColor Red
        if ($cur -eq 'MIXED') { Write-Host '   兩檔切一半：先跑 -Off 還原成 V8，再重跑 -On。' }
        exit 1
    }
    foreach ($n in $names) {
        if (-not (Test-Path -LiteralPath (Join-Path $v9dir $n))) { Write-Host "❌ 缺 V9 來源：$n" -ForegroundColor Red; exit 1 }
        $fork = Get-ForkBase $n; $now = Sha (Join-Path $common $n)
        if (-not $fork) { Write-Host "❌ FORK-BASE.txt 沒有 $n 的基準" -ForegroundColor Red; exit 1 }
        if ($now -ne $fork -and -not $Force) {
            Write-Host "❌ V8 的 $n 自分叉後已被改過——直接切 V9 會退掉那些修正。先 diff 補進 common/v9/，確定無視請加 -Force。" -ForegroundColor Red
            exit 1
        }
    }
    New-Item -ItemType Directory -Force -Path $bakdir | Out-Null
    foreach ($n in $names) {
        Copy-Item -LiteralPath (Join-Path $common $n) -Destination (Join-Path $bakdir $n) -Force
        Copy-Item -LiteralPath (Join-Path $v9dir $n) -Destination (Join-Path $common $n) -Force
    }
    if ((Invoke-RulesCheck) -ne 0) {
        Write-Host '❌ 切到 V9 後 rules_check 未通過，自動還原 V8。' -ForegroundColor Red
        foreach ($n in $names) { Copy-Item -LiteralPath (Join-Path $bakdir $n) -Destination (Join-Path $common $n) -Force }
        exit 1
    }
    Write-Host '✅ 已切到 V9（下一輪生效）。退回：pwsh -File scripts\s2_v9_switch.ps1 -Off' -ForegroundColor Green
    exit 0
}

if ($Off) {
    $cur = Get-LiveVersion
    if ($cur -eq 'V8') { Write-Host '已經是 V8，不必再切。' -ForegroundColor Green; exit 0 }
    # UNKNOWN／MISSING＝版頭被改過或缺檔，不是本支切出來的狀態；蓋掉可能丟別人的修改。
    # 逐檔檢查：MIXED 裡若有一檔是手改版頭（UNKNOWN），整體判定看不出來，蓋掉會丟修改。
    $odd = @($names | Where-Object { (Get-FileVersion (Join-Path $common $_)) -notin @('V8', 'V9') })
    if ($odd.Count -gt 0 -and -not $Force) {
        Write-Host "❌ 這些檔版頭不是 V8／V9（可能有人手改過）：$($odd -join '、')。先 git diff 確認；確定要用 V8 備份蓋掉請加 -Force。" -ForegroundColor Red
        exit 1
    }
    if ($cur -in @('UNKNOWN', 'MISSING') -and -not $Force) {
        Write-Host "❌ live 版頭是 $cur（不是 V9／MIXED），可能有人手改過。先 git diff 確認；確定要用 V8 備份蓋掉請加 -Force。" -ForegroundColor Red
        exit 1
    }
    foreach ($n in $names) {
        $bak = Join-Path $bakdir $n
        if (-not (Test-Path -LiteralPath $bak)) { Write-Host "❌ 缺 V8 備份：$bak（改用 git 還原）" -ForegroundColor Red; exit 1 }
        if ((Get-FileVersion $bak) -ne 'V8') { Write-Host "❌ 備份檔不是 V8 版頭：$bak" -ForegroundColor Red; exit 1 }
    }
    foreach ($n in $names) { Copy-Item -LiteralPath (Join-Path $bakdir $n) -Destination (Join-Path $common $n) -Force }
    if ((Invoke-RulesCheck) -ne 0) { Write-Host '⚠️ 已還原 V8，但 rules_check 未通過——先回報使用者，不要開始掃帶。' -ForegroundColor Yellow; exit 1 }
    Write-Host '✅ 已退回 V8（下一輪生效）。' -ForegroundColor Green
    exit 0
}
