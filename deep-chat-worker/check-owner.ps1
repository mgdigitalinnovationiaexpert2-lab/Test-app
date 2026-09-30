param([string]$AccountName, [switch]$FunctionsOnly)
$ErrorActionPreference = 'Stop'

function Assert-OwnerIdentity($CurrentSid, $ExpectedSid, $Enabled, $Groups) {
    if (-not $Enabled -or $CurrentSid -ne $ExpectedSid -or
        $Groups -contains 'S-1-5-32-544' -or $ExpectedSid -match '-500$') {
        throw 'OWNER_IDENTITY_REQUIRED'
    }
}

function Test-EdgeProfilePath([string]$Path, [string]$Root) {
    $profile = [IO.Path]::GetFullPath((Join-Path $Root 'profile')).TrimEnd('\')
    $candidate = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    return ($candidate.Equals($profile, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith($profile + '\', [StringComparison]::OrdinalIgnoreCase))
}

function Test-ApprovedEdgeCapabilityRule($Rule) {
    $sid = $Rule.IdentityReference.Value
    # Pin the owner-confirmed Edge capability; a capability prefix alone is not approval.
    $approvedSid = 'S-1-15-3-1024-3239966617-1410756637-3494353204-65451782-2225605771-3526040376-1730753648-3419555762'
    if ($Rule.AccessControlType -ne 'Allow' -or $sid -notmatch '^S-1-15-3-' -or $sid -ne $approvedSid) {
        return $false
    }
    $allowedRights = [int64]([Security.AccessControl.FileSystemRights]::Modify -bor
        [Security.AccessControl.FileSystemRights]::Synchronize)
    $rights = [int64]$Rule.FileSystemRights
    if ($rights -eq -536805376) {
        return (($Rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0 -and
            $Rule.InheritanceFlags -ne [Security.AccessControl.InheritanceFlags]::None)
    }
    return ($rights -gt 0 -and ($rights -band (-bnot $allowedRights)) -eq 0)
}

function Assert-PrivateAcl($Acl, $OwnerSid, [bool]$IsDirectory, [bool]$AllowEdgeCapabilities = $false) {
    $owner = $Acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -notin @($OwnerSid, 'S-1-5-18')) { throw 'OWNER_ACL_UNSAFE' }
    $ownerFull = $false
    foreach ($rule in $Acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($AllowEdgeCapabilities -and $rule.IdentityReference.Value -eq 'S-1-1-0' -and
            $rule.AccessControlType -eq 'Deny' -and
            [int64]$rule.FileSystemRights -eq [int64][Security.AccessControl.FileSystemRights]::Traverse) {
            continue
        }
        if ($rule.AccessControlType -ne 'Allow') { throw 'OWNER_ACL_UNSAFE' }
        if ($AllowEdgeCapabilities -and $rule.IdentityReference.Value -eq 'S-1-5-32-544' -and
            [int64]$rule.FileSystemRights -eq [int64][Security.AccessControl.FileSystemRights]::FullControl -and
            $rule.PropagationFlags -eq [Security.AccessControl.PropagationFlags]::None -and
            [int]$rule.InheritanceFlags -in @(0, 3)) {
            # Edge-created profile ACE only; this cannot satisfy the owner FullControl check.
            continue
        }
        if ($rule.IdentityReference.Value -notin @($OwnerSid, 'S-1-5-18') -and
            -not ($AllowEdgeCapabilities -and (Test-ApprovedEdgeCapabilityRule $rule))) {
            throw 'OWNER_ACL_UNSAFE'
        }
        if ($rule.IdentityReference.Value -eq $OwnerSid -and
            -not ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -and
            ($rule.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq
            [Security.AccessControl.FileSystemRights]::FullControl) {
            if (-not $IsDirectory -or
                ($rule.InheritanceFlags -band 3) -eq 3) { $ownerFull = $true }
        }
    }
    if (-not $ownerFull) { throw 'OWNER_ACL_UNSAFE' }
}

if ($FunctionsOnly) { return }
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if ($identity.Name -ne ([Environment]::MachineName + '\' + $AccountName)) {
        throw 'OWNER_IDENTITY_REQUIRED'
    }
    $account = Get-LocalUser -Name $AccountName
    Assert-OwnerIdentity $identity.User.Value $account.SID.Value $account.Enabled $identity.Groups.Value
    $sid = $account.SID.Value
    $profileKey = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\' + $sid
    $profileHome = [Environment]::ExpandEnvironmentVariables((Get-ItemProperty -LiteralPath $profileKey).ProfileImagePath)
    $root = Join-Path $profileHome 'AppData\Local\Maghsoud\DeepChatPrototype'
    $paths = @($root, (Join-Path $root 'profile'), (Join-Path $root 'state'), (Join-Path $root 'runtime'))
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw 'OWNER_ACL_UNSAFE' }
    }
    # Reject junctions in ancestors before traversing the private root.
    $parent = Get-Item -LiteralPath $root -Force
    while ($null -ne $parent) {
        if ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'OWNER_ACL_UNSAFE' }
        $parent = $parent.Parent
    }
    if (-not (Get-Acl -LiteralPath $root).AreAccessRulesProtected) { throw 'OWNER_ACL_UNSAFE' }
    $queue = [Collections.Generic.Queue[string]]::new()
    $queue.Enqueue($root)
    while ($queue.Count -gt 0) {
        $path = $queue.Dequeue()
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'OWNER_ACL_UNSAFE' }
        $acl = Get-Acl -LiteralPath $path
        Assert-PrivateAcl $acl $sid $item.PSIsContainer (Test-EdgeProfilePath $path $root)
        if ($item.PSIsContainer) {
            foreach ($child in Get-ChildItem -LiteralPath $path -Force) { $queue.Enqueue($child.FullName) }
        }
    }
    @{state='OWNER_BOUNDARY_VALID'; root=$root} | ConvertTo-Json -Compress
} catch {
    $code = 'OWNER_ACL_UNSAFE'
    if ($_.Exception.Message -eq 'OWNER_IDENTITY_REQUIRED') { $code = 'OWNER_IDENTITY_REQUIRED' }
    @{state=$code} | ConvertTo-Json -Compress
    exit 1
}
