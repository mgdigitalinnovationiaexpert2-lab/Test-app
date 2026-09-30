$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'run-owner.ps1') -FunctionsOnly
$testRoot = Join-Path $PSScriptRoot ('.test-runtime\launcher-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $testRoot 'runtime') -Force | Out-Null
$script:events = [Collections.Generic.List[string]]::new()
$script:boundaryState = 'OWNER_ACL_UNSAFE'
$script:checks = 0
function Invoke-DeepChatBoundaryCheck([string]$Folder, [string]$Account) {
    $script:events.Add('validate')
    return [pscustomobject]@{state=$script:boundaryState; root=$testRoot}
}
function Invoke-DeepChatPython([string]$Folder, [string]$Metadata, [string[]]$WorkerArguments) {
    if ($script:events.Count -ne 1 -or $script:events[0] -ne 'validate') { throw 'ORDER_FAILURE' }
    $script:events.Add('python')
    $handoff = $Metadata | ConvertFrom-Json
    $saved = Get-Content -LiteralPath (Join-Path (Join-Path $testRoot 'runtime') $handoff.ticket) -Raw | ConvertFrom-Json
    if ($saved.state -cne 'OWNER_BOUNDARY_VALID' -or $saved.root -ne $testRoot) { throw 'HANDOFF_FAILURE' }
    if (($WorkerArguments -join ',') -ne 'status,--task,synthetic') { throw 'ARGUMENT_FAILURE' }
}
foreach ($state in @('OWNER_ACL_UNSAFE', 'OWNER_IDENTITY_REQUIRED', 'owner_boundary_valid', 'UNKNOWN_SAFE_STOP')) {
    $script:boundaryState = $state
    $script:events.Clear()
    $failed = $false
    try { Invoke-DeepChatOwner $PSScriptRoot 'MGDeepChatOwner' @('status', '--task', 'synthetic') }
    catch { $failed = $true }
    if (-not $failed -or ($script:events -join ',') -ne 'validate') { throw 'INVALID_BOUNDARY_LAUNCHED_PYTHON' }
    if (@(Get-ChildItem -LiteralPath (Join-Path $testRoot 'runtime')).Count -ne 0) { throw 'UNEXPECTED_HANDOFF' }
    $script:checks++
}
$script:boundaryState = 'OWNER_BOUNDARY_VALID'
$script:events.Clear()
Invoke-DeepChatOwner $PSScriptRoot 'MGDeepChatOwner' @('status', '--task', 'synthetic')
if (($script:events -join ',') -ne 'validate,python') { throw 'VALID_BOUNDARY_ORDER_FAILURE' }
if (@(Get-ChildItem -LiteralPath (Join-Path $testRoot 'runtime')).Count -ne 0) { throw 'HANDOFF_NOT_CLEANED' }
$script:checks++
# Remove only the two known empty synthetic directories, never owner state.
Remove-Item -LiteralPath (Join-Path $testRoot 'runtime')
Remove-Item -LiteralPath $testRoot
Write-Output "PASS: $script:checks offline launcher checks; Python/browser not launched."
