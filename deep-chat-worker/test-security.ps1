$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'check-owner.ps1') -FunctionsOnly
$ownerSid = 'S-1-5-21-100-200-300-1001'
$checks = 0
function Must-Fail([scriptblock]$Action, [string]$Expected) {
    try { & $Action } catch {
        if ($_.Exception.Message -eq $Expected) { return }
        throw
    }
    throw 'Expected safe rejection'
}
Assert-OwnerIdentity $ownerSid $ownerSid $true @('S-1-5-32-545')
$checks++
Must-Fail { Assert-OwnerIdentity 'S-1-5-21-100-200-300-500' $ownerSid $true @() } 'OWNER_IDENTITY_REQUIRED'
$checks++
Must-Fail { Assert-OwnerIdentity $ownerSid $ownerSid $true @('S-1-5-32-544') } 'OWNER_IDENTITY_REQUIRED'
$checks++
Must-Fail { Assert-OwnerIdentity $ownerSid $ownerSid $false @() } 'OWNER_IDENTITY_REQUIRED'
$checks++
function New-TestAcl {
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner([Security.Principal.SecurityIdentifier]::new($ownerSid))
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($ownerSid, 'S-1-5-18')) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($sid), 'FullControl',
            'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    return $acl
}
$acl = New-TestAcl
Assert-PrivateAcl $acl $ownerSid $true
$checks++
foreach ($broadSid in @('S-1-1-0', 'S-1-5-11', 'S-1-5-32-545', 'S-1-5-32-544', 'S-1-5-21-100-200-300-1002')) {
    $unsafe = New-TestAcl
    $unsafe.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        [Security.Principal.SecurityIdentifier]::new($broadSid), 'Read', 'Allow'))
    Must-Fail { Assert-PrivateAcl $unsafe $ownerSid $true } 'OWNER_ACL_UNSAFE'
    $checks++
}
$unsafe = New-TestAcl
$unsafe.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-545'))
Must-Fail { Assert-PrivateAcl $unsafe $ownerSid $true } 'OWNER_ACL_UNSAFE'
$checks++
$capabilitySid = 'S-1-15-3-1024-3239966617-1410756637-3494353204-65451782-2225605771-3526040376-1730753648-3419555762'
$syntheticRoot = 'C:\SyntheticDeepChatOwner\DeepChatPrototype'
function New-CapabilityAcl([string]$Sid = $capabilitySid, [string]$Type = 'Allow', [string]$Rights = 'Modify, Synchronize') {
    $acl = New-TestAcl
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        [Security.Principal.SecurityIdentifier]::new($Sid), $Rights, $Type))
    return $acl
}

# Exercise the same path classification used by the real ACL traversal.
foreach ($relative in @('profile', 'profile\Default\Cache', 'profile\Default\Cache\entry')) {
    $allowed = Test-EdgeProfilePath (Join-Path $syntheticRoot $relative) $syntheticRoot
    if (-not $allowed) { throw 'PROFILE_SCOPE_REJECTED' }
    Assert-PrivateAcl (New-CapabilityAcl) $ownerSid $true $allowed
    $checks++
}
foreach ($relative in @('', 'state', 'runtime', 'state\task-conversations.sqlite',
    'runtime\owner-ready', 'runtime\worker.lock', 'runtime\launch-synthetic.json',
    'profile-other', 'profile\..\state')) {
    $path = if ($relative) { Join-Path $syntheticRoot $relative } else { $syntheticRoot }
    $allowed = Test-EdgeProfilePath $path $syntheticRoot
    if ($allowed) { throw 'CAPABILITY_SCOPE_ESCAPED' }
    Must-Fail { Assert-PrivateAcl (New-CapabilityAcl) $ownerSid $true $allowed } 'OWNER_ACL_UNSAFE'
    $checks++
}
foreach ($broadSid in @('S-1-1-0', 'S-1-5-32-545', 'S-1-5-11', 'S-1-5-32-546',
    'S-1-5-32-544', 'S-1-5-21-100-200-300-1002', 'S-1-15-2-1', 'S-1-15-3-1')) {
    Must-Fail { Assert-PrivateAcl (New-CapabilityAcl $broadSid) $ownerSid $true $true } 'OWNER_ACL_UNSAFE'
    $checks++
}
Assert-PrivateAcl (New-TestAcl) $ownerSid $true $true
$checks++
Must-Fail { Assert-PrivateAcl (New-CapabilityAcl $capabilitySid 'Deny') $ownerSid $true $true } 'OWNER_ACL_UNSAFE'
$checks++
Must-Fail { Assert-PrivateAcl (New-CapabilityAcl $capabilitySid 'Allow' 'FullControl') $ownerSid $true $true } 'OWNER_ACL_UNSAFE'
$checks++
$inheritOnly = New-CapabilityAcl
$inheritOnly.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    [Security.Principal.SecurityIdentifier]::new($capabilitySid), 'Modify, Synchronize',
    'ContainerInherit,ObjectInherit', 'InheritOnly', 'Allow'))
Assert-PrivateAcl $inheritOnly $ownerSid $true $true
$checks++
$capabilityOwner = New-CapabilityAcl
$capabilityOwner.SetOwner([Security.Principal.SecurityIdentifier]::new($capabilitySid))
Must-Fail { Assert-PrivateAcl $capabilityOwner $ownerSid $true $true } 'OWNER_ACL_UNSAFE'
$checks++
function New-RawInventoryAcl([string]$Ace) {
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $sddl = 'O:' + $ownerSid + 'G:SYD:P(A;OICI;FA;;;' + $ownerSid + ')(A;OICI;FA;;;SY)' + $Ace
    $acl.SetSecurityDescriptorSddlForm($sddl)
    return $acl
}
foreach ($form in @(@('', '0x1301bf'), @('ID', '0x1301bf'),
                    @('OICIIO', '0xe0010000'), @('OICIIOID', '0xe0010000'))) {
    $inventoryAcl = New-RawInventoryAcl ('(A;' + $form[0] + ';' + $form[1] + ';;;' + $capabilitySid + ')')
    Assert-PrivateAcl $inventoryAcl $ownerSid $true $true
    $checks++
    foreach ($relative in @('', 'state', 'runtime')) {
        $path = if ($relative) { Join-Path $syntheticRoot $relative } else { $syntheticRoot }
        Must-Fail { Assert-PrivateAcl $inventoryAcl $ownerSid $true (Test-EdgeProfilePath $path $syntheticRoot) } 'OWNER_ACL_UNSAFE'
        $checks++
    }
}
foreach ($flags in @('', 'ID')) {
    $invalidGeneric = New-RawInventoryAcl ('(A;' + $flags + ';0xe0010000;;;' + $capabilitySid + ')')
    Must-Fail { Assert-PrivateAcl $invalidGeneric $ownerSid $true $true } 'OWNER_ACL_UNSAFE'
    $checks++
}
$everyoneTraverse = New-RawInventoryAcl '(D;;0x20;;;WD)'
foreach ($relative in @('profile\Default\Local Storage\leveldb\synthetic', 'profile\Default\Session Storage\synthetic')) {
    Assert-PrivateAcl $everyoneTraverse $ownerSid $false (Test-EdgeProfilePath (Join-Path $syntheticRoot $relative) $syntheticRoot)
    $checks++
}
foreach ($relative in @('', 'state', 'runtime', 'state\task-conversations.sqlite', 'runtime\owner-ready',
    'runtime\worker.lock', 'runtime\launch-synthetic.json', 'profile-other', 'profile\..\state')) {
    $path = if ($relative) { Join-Path $syntheticRoot $relative } else { $syntheticRoot }
    Must-Fail { Assert-PrivateAcl $everyoneTraverse $ownerSid $false (Test-EdgeProfilePath $path $syntheticRoot) } 'OWNER_ACL_UNSAFE'
    $checks++
}
foreach ($ace in @('(A;;0x20;;;WD)', '(D;;0x301bf;;;WD)', '(D;;FA;;;WD)', '(D;;FR;;;WD)', '(D;;0x21;;;WD)')) {
    Must-Fail { Assert-PrivateAcl (New-RawInventoryAcl $ace) $ownerSid $false $true } 'OWNER_ACL_UNSAFE'
    $checks++
}
$everyoneOwner = New-RawInventoryAcl '(D;;0x20;;;WD)'
$everyoneOwner.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-1-0'))
Must-Fail { Assert-PrivateAcl $everyoneOwner $ownerSid $false $true } 'OWNER_ACL_UNSAFE'
$checks++
foreach ($flags in @('OICI', '', 'OICIID', 'ID')) {
    $adminAcl = New-RawInventoryAcl ('(A;' + $flags + ';FA;;;BA)')
    Assert-PrivateAcl $adminAcl $ownerSid $true (Test-EdgeProfilePath (Join-Path $syntheticRoot 'profile\Default\Extensions') $syntheticRoot)
    $checks++
    foreach ($relative in @('', 'state', 'runtime', 'state\task-conversations.sqlite',
        'runtime\owner-ready', 'runtime\worker.lock', 'runtime\launch-synthetic.json',
        'profile-other', 'profile\..\state')) {
        $path = if ($relative) { Join-Path $syntheticRoot $relative } else { $syntheticRoot }
        Must-Fail { Assert-PrivateAcl $adminAcl $ownerSid $true (Test-EdgeProfilePath $path $syntheticRoot) } 'OWNER_ACL_UNSAFE'
        $checks++
    }
}
$adminOwner = New-RawInventoryAcl '(A;OICI;FA;;;BA)'
$adminOwner.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
Must-Fail { Assert-PrivateAcl $adminOwner $ownerSid $true $true } 'OWNER_ACL_UNSAFE'
$checks++
foreach ($ace in @('(D;;FA;;;BA)', '(A;;0x1301bf;;;BA)', '(A;;FA;;;BU)', '(A;;FA;;;AU)',
    '(A;;FA;;;BG)', '(A;;FA;;;S-1-5-21-100-200-300-1002)', '(A;OI;FA;;;BA)',
    '(A;CI;FA;;;BA)', '(A;OICIIO;FA;;;BA)', '(A;OICINP;FA;;;BA)')) {
    Must-Fail { Assert-PrivateAcl (New-RawInventoryAcl $ace) $ownerSid $true $true } 'OWNER_ACL_UNSAFE'
    $checks++
}
$noOwnerAccess = [Security.AccessControl.DirectorySecurity]::new()
$noOwnerAccess.SetSecurityDescriptorSddlForm(('O:' + $ownerSid + 'G:SYD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)'))
Must-Fail { Assert-PrivateAcl $noOwnerAccess $ownerSid $true $true } 'OWNER_ACL_UNSAFE'
$checks++
Write-Output "PASS: $checks offline identity/ACL checks; no accounts or filesystem ACLs changed."
