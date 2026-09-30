$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'owner-config.json') -Raw | ConvertFrom-Json
. (Join-Path $PSScriptRoot 'check-owner.ps1') -FunctionsOnly
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($identity.Name -ne ([Environment]::MachineName + '\' + $config.windows_local_account)) {
    throw 'OWNER_IDENTITY_REQUIRED'
}
$account = Get-LocalUser -Name $config.windows_local_account
Assert-OwnerIdentity $identity.User.Value $account.SID.Value $account.Enabled $identity.Groups.Value
$profileKey = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\' + $account.SID.Value
$profileHome = [Environment]::ExpandEnvironmentVariables((Get-ItemProperty -LiteralPath $profileKey).ProfileImagePath)
$root = Join-Path $profileHome 'AppData\Local\Maghsoud\DeepChatPrototype'
if (Test-Path -LiteralPath $root) { throw 'EXISTING_RUNTIME_REQUIRES_OWNER_REVIEW_DO_NOT_RESET' }
$acl = [Security.AccessControl.DirectorySecurity]::new()
$acl.SetOwner($account.SID)
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($account.SID, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
New-Item -ItemType Directory -Path $root | Out-Null
Set-Acl -LiteralPath $root -AclObject $acl
foreach ($name in @('profile', 'state', 'runtime')) {
    New-Item -ItemType Directory -Path (Join-Path $root $name) | Out-Null
}
& (Join-Path $PSScriptRoot 'check-owner.ps1') -AccountName $config.windows_local_account
