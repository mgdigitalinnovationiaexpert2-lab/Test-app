param(
    [ValidateSet('owner-login', 'status', 'certify', 'task-status', 'recover-first-turn')][string]$Command = 'status',
    [ValidatePattern('^[A-Za-z0-9_-]{1,64}$')][string]$Task = 'synthetic-certification-001',
    [switch]$ApproveTwoSyntheticMessages,
    [switch]$FunctionsOnly
)
$ErrorActionPreference = 'Stop'

function Invoke-DeepChatBoundaryCheck([string]$Folder, [string]$Account) {
    # Run in this PowerShell context, never beneath the venv Python process.
    $output = @(& (Join-Path $Folder 'check-owner.ps1') -AccountName $Account)
    if (-not $? -or $output.Count -ne 1) { throw 'OWNER_BOUNDARY_UNVERIFIED' }
    return ($output[0] | ConvertFrom-Json)
}

function Invoke-DeepChatPython([string]$Folder, [string]$Metadata, [string[]]$WorkerArguments) {
    $python = Join-Path $Folder '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'OWNER_PYTHON_UNAVAILABLE' }
    $previous = [Environment]::GetEnvironmentVariable('MG_DEEP_CHAT_LAUNCH', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('MG_DEEP_CHAT_LAUNCH', $Metadata, 'Process')
        & $python -I (Join-Path $Folder 'worker.py') @WorkerArguments
        if ($LASTEXITCODE -ne 0) { throw 'OWNER_WORKER_STOPPED' }
    } finally {
        [Environment]::SetEnvironmentVariable('MG_DEEP_CHAT_LAUNCH', $previous, 'Process')
    }
}

function Invoke-DeepChatOwner([string]$Folder, [string]$Account, [string[]]$WorkerArguments) {
    $boundary = Invoke-DeepChatBoundaryCheck $Folder $Account
    if ($boundary.state -cne 'OWNER_BOUNDARY_VALID') {
        if ($boundary.state -cin @('OWNER_ACL_UNSAFE', 'OWNER_IDENTITY_REQUIRED')) { throw $boundary.state }
        throw 'OWNER_BOUNDARY_UNVERIFIED'
    }
    if ([string]::IsNullOrWhiteSpace($boundary.root) -or -not [IO.Path]::IsPathRooted($boundary.root)) {
        throw 'OWNER_BOUNDARY_UNVERIFIED'
    }
    # The checked root is private. The one-use handoff contains no browser/session data.
    $ticketName = 'launch-' + [guid]::NewGuid().ToString('N') + '.json'
    $ticketPath = Join-Path (Join-Path $boundary.root 'runtime') $ticketName
    $metadata = @{state='OWNER_BOUNDARY_VALID'; root=$boundary.root; ticket=$ticketName;
        created_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()} | ConvertTo-Json -Compress
    $stream = $null
    try {
        $stream = [IO.File]::Open($ticketPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $bytes = [Text.Encoding]::UTF8.GetBytes($metadata)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
        $stream.Dispose()
        $stream = $null
        Invoke-DeepChatPython $Folder $metadata $WorkerArguments
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if (Test-Path -LiteralPath $ticketPath -PathType Leaf) { Remove-Item -LiteralPath $ticketPath }
    }
}

if ($FunctionsOnly) { return }
try {
    $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'owner-config.json') -Raw | ConvertFrom-Json
    if ($config.windows_local_account -cnotmatch '^MGDeepChatOwner[A-Za-z0-9_-]*$') {
        throw 'OWNER_CONFIGURATION_INVALID'
    }
    $workerArguments = @($Command, '--task', $Task)
    if ($ApproveTwoSyntheticMessages) { $workerArguments += '--approve-two-synthetic-messages' }
    Invoke-DeepChatOwner $PSScriptRoot $config.windows_local_account $workerArguments
} catch {
    $code = $_.Exception.Message
    if ($code -cnotin @('OWNER_ACL_UNSAFE', 'OWNER_IDENTITY_REQUIRED', 'OWNER_BOUNDARY_UNVERIFIED',
        'OWNER_CONFIGURATION_INVALID', 'OWNER_PYTHON_UNAVAILABLE', 'OWNER_WORKER_STOPPED')) {
        $code = 'OWNER_LAUNCHER_STOPPED'
    }
    @{state=$code} | ConvertTo-Json -Compress
    exit 1
}
