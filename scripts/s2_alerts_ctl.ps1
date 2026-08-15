#Requires -Version 7
<#
.SYNOPSIS
  快訊守護開關。預設關閉；只有 -On 才會跑。不登錄開機排程。

.EXAMPLE
  pwsh -File scripts\s2_alerts_ctl.ps1 -Status
  pwsh -File scripts\s2_alerts_ctl.ps1 -On
  pwsh -File scripts\s2_alerts_ctl.ps1 -Off
  pwsh -File scripts\s2_alerts_ctl.ps1 -OnceDry
#>
[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(ParameterSetName = 'On')][switch]$On,
    [Parameter(ParameterSetName = 'Off')][switch]$Off,
    [Parameter(ParameterSetName = 'Status')][switch]$Status,
    [Parameter(ParameterSetName = 'OnceDry')][switch]$OnceDry,
    [string]$FlagFile = "$env:USERPROFILE\.s2-alerts-enabled",
    [string]$NodeScript = "$PSScriptRoot\s2_alerts.js"
)

function Get-AlertsPid {
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like '*s2_alerts.js*' } |
        Select-Object -ExpandProperty ProcessId
}

function Start-Alerts {
    $running = @(Get-AlertsPid)
    if ($running.Count -gt 0) {
        Write-Host "守護已在跑（PID $($running -join ', ')）"
        return
    }
    $wd = Split-Path $NodeScript
    $p = Start-Process -FilePath 'node.exe' -ArgumentList @("`"$NodeScript`"") `
        -WorkingDirectory $wd -WindowStyle Hidden -PassThru
    Write-Host "已啟動快訊守護 PID $($p.Id)（每 90 秒一輪，旗標撤掉會自己停）"
}

function Stop-Alerts {
    $pids = @(Get-AlertsPid)
    foreach ($id in $pids) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
    if ($pids.Count -gt 0) { Write-Host "已停止 PID $($pids -join ', ')" }
    else { Write-Host "沒有在跑的守護行程" }
}

if ($OnceDry) {
    Write-Host "測一輪（--once --dry-run --force，不推播、不改旗標）"
    & node.exe $NodeScript --once --dry-run --force
    exit $LASTEXITCODE
}

if ($On) {
    Set-Content -Path $FlagFile -Value (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') -Encoding utf8
    Start-Alerts
    Write-Host "快訊守護：ON（旗標 $FlagFile）"
    Write-Host "這次沒登錄開機排程；重開機後要再 -On。"
} elseif ($Off) {
    if (Test-Path $FlagFile) { Remove-Item $FlagFile -Force }
    Stop-Alerts
    Write-Host "快訊守護：OFF"
} else {
    $pids = @(Get-AlertsPid)
    if (Test-Path $FlagFile) {
        $since = (Get-Content $FlagFile -Raw).Trim()
        Write-Host "旗標：ON（自 $since）／行程：$(if ($pids) { $pids -join ',' } else { '未在跑' })"
    } else {
        Write-Host "旗標：OFF（預設）／行程：$(if ($pids) { $pids -join ',' } else { '未在跑' })"
    }
}
