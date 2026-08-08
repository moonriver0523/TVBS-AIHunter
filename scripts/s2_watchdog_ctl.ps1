#Requires -Version 7
<#
.SYNOPSIS
  S2 看門狗開關——on demand 啟用/停用，不改任何排程設定本身。

.EXAMPLE
  pwsh -File scripts\s2_watchdog_ctl.ps1 -On
.EXAMPLE
  pwsh -File scripts\s2_watchdog_ctl.ps1 -Off
.EXAMPLE
  pwsh -File scripts\s2_watchdog_ctl.ps1 -Status
#>
[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(ParameterSetName = 'On')][switch]$On,
    [Parameter(ParameterSetName = 'Off')][switch]$Off,
    [Parameter(ParameterSetName = 'Status')][switch]$Status,
    [string]$FlagFile = "$env:USERPROFILE\.s2-watchdog-enabled"
)

if ($On) {
    Set-Content -Path $FlagFile -Value (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') -Encoding UTF8
    Write-Host "看門狗已開啟（旗標檔：$FlagFile）"
} elseif ($Off) {
    if (Test-Path $FlagFile) { Remove-Item $FlagFile -Force }
    Write-Host "看門狗已關閉"
} else {
    if (Test-Path $FlagFile) {
        $since = Get-Content $FlagFile -Raw
        Write-Host "看門狗目前：開啟（自 $since 起）"
    } else {
        Write-Host "看門狗目前：關閉"
    }
}
