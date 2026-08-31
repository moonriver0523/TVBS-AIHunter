#Requires -Version 7
<#
.SYNOPSIS
  S2 掃帶 V4（三站）⇄ V5（四站，含 ENEX）一鍵切換。預設唯讀，只印狀態。

.DESCRIPTION
  **切換方式＝換掉 prompt 檔本身，不動排程、不動 s2_scan.ps1。**

  為什麼不是改排程任務的引數：`s2_watchdog.ps1:329-333` 代打時是**自己組一份
  引數列**去叫 `s2_scan.ps1`（`-NoProfile -File … -Checkpoint … -Model sonnet`），
  裡面沒有 `-PromptFile`。只改排程任務的話，主排程走 V5、看門狗代打卻走 V4，
  兩條路會不一致。改 prompt 檔本身，兩條路都吃到同一版，零遺漏。

  這也跟 repo 既有的回滾慣例一致（`tc_v2_rollback.ps1` 走 git checkout 取檔）。

  V5 上線後**不必**重啟排程、看門狗或保活——prompt 是每輪開跑時才讀的。

.EXAMPLE
  pwsh -File scripts\s2_v5_switch.ps1              # 看狀態（預設，唯讀）
  pwsh -File scripts\s2_v5_switch.ps1 -On          # 切到 V5（四站）
  pwsh -File scripts\s2_v5_switch.ps1 -Off         # 退回 V4（三站）
#>
[CmdletBinding()]
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Force,                # 略過「輪次可能在跑」與「v4 漂移」兩道警告
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter'
)

$ErrorActionPreference = 'Stop'

$live   = Join-Path $Repo 'scripts\s2_scan_prompt.md'      # 排程與看門狗實際讀的那份
$v5src  = Join-Path $Repo 'scripts\s2_scan_prompt_v5.md'
$bak    = Join-Path $Repo 'scripts\_s2_scan_prompt_v4.bak.md'
$rule13g= Join-Path $Repo 'common\13g-S2-定時掃帶-v5-四站.md'
$lock   = "$env:USERPROFILE\.s2-scan.lock"

# 🔴 2026-09-01：雜湊前先把行尾正規化成 LF。
# 本 repo 開著 autocrlf，git 一旦重寫行尾，同一份內容的位元組雜湊就會變——
# 那會在「要上線那天」假報「V4 prompt 漂移」把 -On 擋掉，
# 而真正該擋的是**內容**變了，不是行尾。⛔ 不要改回直接 Get-FileHash。
function Sha([string]$p) {
    if (-not (Test-Path $p)) { return $null }
    $text = [System.IO.File]::ReadAllText($p) -replace "`r`n", "`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }
    finally { $sha.Dispose() }
}

# V5 prompt 檔尾記著分叉當下 v4 的 sha256；用來偵測「V4 後來又改過、V5 沒跟上」。
function Get-ForkBase {
    if (-not (Test-Path $v5src)) { return $null }
    $m = [regex]::Match((Get-Content $v5src -Raw), 'V5-FORK-BASE .*?sha256=([0-9a-f]{64})')
    if ($m.Success) { return $m.Groups[1].Value } else { return $null }
}

function Get-LiveVersion {
    if (-not (Test-Path $live)) { return 'MISSING' }
    if ((Get-Content $live -Raw) -match '這是 V5（四站）版') { return 'V5' } else { return 'V4' }
}

# ⛔ 只看鎖檔存不存在，絕不開檔——開檔會搶到 s2_scan.ps1 的 FileShare::None
#    獨佔握把，害正要啟動的那一輪直接 SKIP（R16／A5 都記過這個坑）。
function Test-Busy { Test-Path $lock }

function Show-Status {
    $ver = Get-LiveVersion
    Write-Host ''
    Write-Host "== S2 掃帶版本狀態 ==" -ForegroundColor Cyan
    Write-Host "生效中     : $ver  ($live)"
    Write-Host "V5 來源    : $(if (Test-Path $v5src) { 'OK' } else { '❌ 缺檔' })  $v5src"
    Write-Host "13g 規則檔 : $(if (Test-Path $rule13g) { 'OK' } else { '❌ 缺檔' })"
    if (Test-Path $rule13g) {
        $eof = (Get-Content $rule13g -Raw) -match 'RULES-EOF 13g'
        Write-Host "13g EOF 標記: $(if ($eof) { 'OK' } else { '❌ 缺 RULES-EOF' })"
    }
    Write-Host "V4 備份    : $(if (Test-Path $bak) { 'OK' } else { '（尚未建立，-On 時會自動建）' })"
    Write-Host "掃帶鎖     : $(if (Test-Busy) { '⚠️ 存在——可能有輪次或保活正在跑' } else { '空閒' })"

    $fork = Get-ForkBase
    if ($ver -eq 'V4' -and $fork) {
        $now = Sha $live
        if ($now -eq $fork) {
            Write-Host "V4 漂移    : 無（與 V5 分叉基準相同）" -ForegroundColor Green
        } else {
            Write-Host "V4 漂移    : ⚠️ V4 prompt 自分叉後已被改過" -ForegroundColor Yellow
            Write-Host "             分叉基準 $fork"
            Write-Host "             目前     $now"
            Write-Host "             → 切換前先 diff 兩份，把 V4 後來的修正補進 V5，否則會退版。"
        }
    }
    Write-Host ''
    Write-Host "ENEX 掃描輪次（13g V5-1）：04:30／07:30／17:00／20:00／22:00（10:00、12:00 跳過）"
    Write-Host ''
}

if ($On -and $Off) { Write-Host "❌ -On 與 -Off 只能擇一" -ForegroundColor Red; exit 1 }

if (-not $On -and -not $Off) { Show-Status; exit 0 }

# ── 共同前置檢查 ────────────────────────────────────────────────────────
# 🔴 2026-09-01 修（獨立複查抓到）：原本寫 `if (Test-Busy -and -not $Force)`，
# PowerShell 會把 `-and -not $Force` 當成**傳給 Test-Busy 的引數**（實測
# 函式內 $args 收到 `-and -not True`），於是 -Force 從來沒有作用過——
# 鎖在時一律被擋，訊息卻叫人加 -Force，加了也一樣。函式呼叫要自己括起來。
if ((Test-Busy) -and -not $Force) {
    Write-Host "⚠️ 偵測到 $lock——輪次或 NS 保活可能正在跑。" -ForegroundColor Yellow
    Write-Host "   prompt 是開跑當下才讀的，換掉不會影響已在跑的那一輪；"
    Write-Host "   但為了乾淨，建議等它跑完。要照換請加 -Force。"
    exit 1
}

if ($On) {
    if ((Get-LiveVersion) -eq 'V5') { Write-Host "已經是 V5，不必再切。" -ForegroundColor Green; exit 0 }
    foreach ($f in @($v5src, $rule13g)) {
        if (-not (Test-Path $f)) { Write-Host "❌ 缺檔，無法切換：$f" -ForegroundColor Red; exit 1 }
    }
    if (-not ((Get-Content $rule13g -Raw) -match 'RULES-EOF 13g')) {
        Write-Host "❌ 13g 檔尾缺 RULES-EOF 標記，agent 無法驗證是否被截斷。" -ForegroundColor Red; exit 1
    }
    $fork = Get-ForkBase; $now = Sha $live
    if ($fork -and $now -ne $fork -and -not $Force) {
        Write-Host "❌ V4 prompt 自分叉後已被改過——直接切 V5 會**退掉那些修正**。" -ForegroundColor Red
        Write-Host "   分叉基準 $fork"
        Write-Host "   目前     $now"
        Write-Host "   先 diff 兩份補齊，再重跑；確定要無視請加 -Force。"
        exit 1
    }

    Copy-Item $live $bak -Force          # 備份現行 V4，-Off 靠它還原
    Copy-Item $v5src $live -Force
    Write-Host "✅ 已切換到 V5（四站：NS／AP／RT ＋ ENEX）" -ForegroundColor Green
    Write-Host "   下一輪自動生效，⛔ 不必重啟排程／看門狗／保活。"
    Write-Host "   備份：$bak（-Off 會用它還原）"
    Write-Host "   ⚠️ 上線後才做的收尾（13g V5-6）：18 §0 拆段、s2_rules_check 加 13g、"
    Write-Host "      s2_token_metrics 加 enex 桶、保活加 ENEX 健康檢查、A9 帳本回寫。"
    exit 0
}

if ($Off) {
    if ((Get-LiveVersion) -eq 'V4') { Write-Host "已經是 V4，不必還原。" -ForegroundColor Green; exit 0 }
    if (-not (Test-Path $bak)) {
        Write-Host "❌ 找不到備份 $bak，無法自動還原。" -ForegroundColor Red
        Write-Host "   手動作法：git -C $Repo checkout -- scripts/s2_scan_prompt.md"
        exit 1
    }
    Copy-Item $bak $live -Force
    Write-Host "✅ 已退回 V4（三站）。下一輪自動生效。" -ForegroundColor Green
    Write-Host "   ⚠️ ENEX 回到「人工下令才跑」，13g 留著不影響（V4 prompt 不會讀它）。"
    exit 0
}
