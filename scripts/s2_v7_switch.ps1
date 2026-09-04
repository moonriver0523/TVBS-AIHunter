#Requires -Version 7
<#
.SYNOPSIS
  S2 掃帶 V5（四站）⇄ V7（五站，含 ABC）一鍵切換。預設唯讀，只印狀態。

.DESCRIPTION
  **照抄 `s2_v5_switch.ps1` 的機制，只換掉版本與檔名。**
  切換方式＝換掉 prompt 檔本身，不動排程、不動 `s2_scan.ps1`——理由見 `s2_v5_switch.ps1`
  的說明（看門狗代打時自己組引數列，裡面沒有 `-PromptFile`，只改排程會兩條路不一致）。

  V7 上線後**不必**重啟排程、看門狗或保活——prompt 是每輪開跑時才讀的。

  🔴 **2026-09-04 建立時尚未獲授權上線。** 檔案躺在 repo 裡對現行輪次零影響
  （V5 prompt 不會提到 `13h`）。要切換請等使用者明確下令。

  ⛔ **V7 生效期間不要跑 `s2_v5_switch.ps1`**：那支的 `Get-LiveVersion` 只認得 V4／V5，
  看到 V7 會報成「V4」，它的 `-On` 會直接把 V7 蓋掉。退版一律用本支的 `-Off`。

.EXAMPLE
  pwsh -File scripts\s2_v7_switch.ps1              # 看狀態（預設，唯讀）
  pwsh -File scripts\s2_v7_switch.ps1 -On          # 切到 V7（五站）
  pwsh -File scripts\s2_v7_switch.ps1 -Off         # 退回 V5（四站）
#>
[CmdletBinding()]
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Force,                # 略過「輪次可能在跑」與「v5 漂移」兩道警告
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter'
)

$ErrorActionPreference = 'Stop'

$live   = Join-Path $Repo 'scripts\s2_scan_prompt.md'      # 排程與看門狗實際讀的那份
$v7src  = Join-Path $Repo 'scripts\s2_scan_prompt_v7.md'
$bak    = Join-Path $Repo 'scripts\_s2_scan_prompt_v5.bak.md'   # ⛔ 不是 v4 那份，別搞混
$rule13g= Join-Path $Repo 'common\13g-S2-定時掃帶-v5-四站.md'
$rule13h= Join-Path $Repo 'common\13h-S2-定時掃帶-v7-五站.md'
$lock   = "$env:USERPROFILE\.s2-scan.lock"

# 🔴 雜湊前先把行尾正規化成 LF（沿用 v5 那支 2026-09-01 的修正）。
# 本 repo 開著 autocrlf，git 一旦重寫行尾，同一份內容的位元組雜湊就會變——
# 那會在「要上線那天」假報「V5 prompt 漂移」把 -On 擋掉，
# 而真正該擋的是**內容**變了，不是行尾。⛔ 不要改回直接 Get-FileHash。
function Sha([string]$p) {
    if (-not (Test-Path $p)) { return $null }
    $text = [System.IO.File]::ReadAllText($p) -replace "`r`n", "`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }
    finally { $sha.Dispose() }
}

# V7 prompt 檔尾記著分叉當下 V5 live 的 sha256；用來偵測「V5 後來又改過、V7 沒跟上」。
# ⚠️ 檔案裡同時留著舊的 `V5-FORK-BASE`（V5 從 V4 分叉的歷史紀錄），
#    所以正則要指名 `V7-FORK-BASE`，⛔ 不可只比對 `FORK-BASE`。
function Get-ForkBase {
    if (-not (Test-Path $v7src)) { return $null }
    $m = [regex]::Match((Get-Content $v7src -Raw), 'V7-FORK-BASE .*?sha256=([0-9a-f]{64})')
    if ($m.Success) { return $m.Groups[1].Value } else { return $null }
}

# 🔴 三段判定，順序有意義：先問是不是 V7，再問是不是 V5，都不是才是 V4。
#    ⛔ 不要簡化成兩段——V7 生效時若被判成 V4，-On 會拿 V5 蓋掉 V7。
function Get-LiveVersion {
    if (-not (Test-Path $live)) { return 'MISSING' }
    $txt = Get-Content $live -Raw
    if ($txt -match '這是 V7（五站）版') { return 'V7' }
    if ($txt -match '這是 V5（四站）版') { return 'V5' }
    return 'V4'
}

# ⛔ 只看鎖檔存不存在，絕不開檔——開檔會搶到 s2_scan.ps1 的 FileShare::None
#    獨佔握把，害正要啟動的那一輪直接 SKIP（R16／A5 都記過這個坑）。
function Test-Busy { Test-Path $lock }

function Show-Status {
    $ver = Get-LiveVersion
    Write-Host ''
    Write-Host "== S2 掃帶版本狀態 ==" -ForegroundColor Cyan
    Write-Host "生效中     : $ver  ($live)"
    Write-Host "V7 來源    : $(if (Test-Path $v7src) { 'OK' } else { '❌ 缺檔' })  $v7src"
    Write-Host "13g 規則檔 : $(if (Test-Path $rule13g) { 'OK' } else { '❌ 缺檔' })"
    Write-Host "13h 規則檔 : $(if (Test-Path $rule13h) { 'OK' } else { '❌ 缺檔' })"
    if (Test-Path $rule13h) {
        $eof = (Get-Content $rule13h -Raw) -match 'RULES-EOF 13h'
        Write-Host "13h EOF 標記: $(if ($eof) { 'OK' } else { '❌ 缺 RULES-EOF' })"
    }
    Write-Host "V5 備份    : $(if (Test-Path $bak) { 'OK' } else { '（尚未建立，-On 時會自動建）' })"
    Write-Host "掃帶鎖     : $(if (Test-Busy) { '⚠️ 存在——可能有輪次或保活正在跑' } else { '空閒' })"

    $fork = Get-ForkBase
    if ($ver -eq 'V5' -and $fork) {
        $now = Sha $live
        if ($now -eq $fork) {
            Write-Host "V5 漂移    : 無（與 V7 分叉基準相同）" -ForegroundColor Green
        } else {
            Write-Host "V5 漂移    : ⚠️ V5 prompt 自分叉後已被改過" -ForegroundColor Yellow
            Write-Host "             分叉基準 $fork"
            Write-Host "             目前     $now"
            Write-Host "             → 切換前先 diff 兩份，把 V5 後來的修正補進 V7，否則會退版。"
        }
    }
    Write-Host ''
    Write-Host "V7 掃描順序：NS → AP → RT → ENEX → ABC（13h V7-1）"
    Write-Host "ENEX 輪次（13g V5-1）：04:30／07:00／17:00／22:00；ABC **每一輪都掃**，無跳過表。"
    if ($ver -eq 'V7') {
        Write-Host "⛔ V7 生效中：不要跑 s2_v5_switch.ps1（它會把 V7 誤判成 V4 並蓋掉）。" -ForegroundColor Yellow
    }
    Write-Host ''
}

if ($On -and $Off) { Write-Host "❌ -On 與 -Off 只能擇一" -ForegroundColor Red; exit 1 }

if (-not $On -and -not $Off) { Show-Status; exit 0 }

# ── 共同前置檢查 ────────────────────────────────────────────────────────
# 🔴 函式呼叫要自己括起來（v5 那支 2026-09-01 修過同一個坑：寫成
# `if (Test-Busy -and -not $Force)` 會把 `-and -not $Force` 當成傳給函式的引數，
# -Force 從來沒有作用過）。
if ((Test-Busy) -and -not $Force) {
    Write-Host "⚠️ 偵測到 $lock——輪次或保活可能正在跑。" -ForegroundColor Yellow
    Write-Host "   prompt 是開跑當下才讀的，換掉不會影響已在跑的那一輪；"
    Write-Host "   但為了乾淨，建議等它跑完。要照換請加 -Force。"
    exit 1
}

if ($On) {
    $cur = Get-LiveVersion
    if ($cur -eq 'V7') { Write-Host "已經是 V7，不必再切。" -ForegroundColor Green; exit 0 }
    if ($cur -ne 'V5') {
        Write-Host "❌ 目前生效的是 $cur，不是 V5。" -ForegroundColor Red
        Write-Host "   本支只負責 V5 ⇄ V7。先用 s2_v5_switch.ps1 -On 切到 V5，再回來切 V7。"
        exit 1
    }
    foreach ($f in @($v7src, $rule13g, $rule13h)) {
        if (-not (Test-Path $f)) { Write-Host "❌ 缺檔，無法切換：$f" -ForegroundColor Red; exit 1 }
    }
    if (-not ((Get-Content $rule13h -Raw) -match 'RULES-EOF 13h')) {
        Write-Host "❌ 13h 檔尾缺 RULES-EOF 標記，agent 無法驗證是否被截斷。" -ForegroundColor Red; exit 1
    }
    $fork = Get-ForkBase; $now = Sha $live
    if ($fork -and $now -ne $fork -and -not $Force) {
        Write-Host "❌ V5 prompt 自分叉後已被改過——直接切 V7 會**退掉那些修正**。" -ForegroundColor Red
        Write-Host "   分叉基準 $fork"
        Write-Host "   目前     $now"
        Write-Host "   先 diff 兩份補齊，再重跑；確定要無視請加 -Force。"
        exit 1
    }

    Copy-Item $live $bak -Force          # 備份現行 V5，-Off 靠它還原
    Copy-Item $v7src $live -Force
    Write-Host "✅ 已切換到 V7（五站：NS／AP／RT／ENEX ＋ ABC）" -ForegroundColor Green
    Write-Host "   下一輪自動生效，⛔ 不必重啟排程／看門狗／保活。"
    Write-Host "   備份：$bak（-Off 會用它還原）"
    Write-Host "   ⛔ 從現在起不要跑 s2_v5_switch.ps1（會把 V7 誤判成 V4 並蓋掉）。"
    Write-Host "   ⚠️ 上線後才做的收尾（13h V7-6）：18 §0 ABC 段拆掉、13g V5-0 改指向 13h、"
    Write-Host "      s2_rules_check 加 13g＋13h、s2_token_metrics 加 enex／abc 桶、A9 帳本回寫。"
    exit 0
}

if ($Off) {
    if ((Get-LiveVersion) -ne 'V7') { Write-Host "目前不是 V7，不必還原。" -ForegroundColor Green; exit 0 }
    if (-not (Test-Path $bak)) {
        Write-Host "❌ 找不到備份 $bak，無法自動還原。" -ForegroundColor Red
        Write-Host "   手動作法：git -C $Repo checkout -- scripts/s2_scan_prompt.md"
        exit 1
    }
    Copy-Item $bak $live -Force
    Write-Host "✅ 已退回 V5（四站）。下一輪自動生效。" -ForegroundColor Green
    Write-Host "   ⚠️ ABC 回到「人工下令才跑」，13h 留著不影響（V5 prompt 不會讀它）。"
    exit 0
}
