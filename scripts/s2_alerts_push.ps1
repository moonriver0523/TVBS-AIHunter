#Requires -Version 7
# 快訊守護的推播出口：只轉呼叫既有 Send-Ntfy，不另開頻道。
param(
    [Parameter(Mandatory)][string]$Body,
    [string]$Title = 'S2 alert',
    [string]$Tags = 'warning',
    [string]$Priority = 'high'
)
. "$PSScriptRoot\s2_notify.ps1"
$err = Send-Ntfy -Body $Body -Title $Title -Tags $Tags -Priority $Priority
if ($err) {
    Write-Output $err
    exit 1
}
exit 0
