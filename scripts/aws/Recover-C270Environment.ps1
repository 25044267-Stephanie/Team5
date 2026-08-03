<#
.SYNOPSIS
  One-command recovery for C270 Jenkins + application EC2 after an AWS Academy restart.

.DESCRIPTION
  Loads temporary AWS Academy CLI credentials from the Windows clipboard (never from chat/files),
  rediscovers current EC2 public IPs, optionally starts instances, repairs managed /32 security-group
  rules for the current client IP, verifies Jenkins/Docker health over SSH, and opens the Jenkins URL.

  Contains no embedded credentials, PEMs, passwords, or fixed public IPs.

.EXAMPLE
  # 1) Start Learner Lab and copy the newest AWS CLI credential block to clipboard
  # 2) Run:
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File ".\scripts\aws\Recover-C270Environment.ps1" `
    -StartInstances -RepairSecurityGroups -RepairJenkins `
    -CheckApplication -CheckJenkins -OpenBrowser
#>
[CmdletBinding()]
param(
    [string]$Region = "us-east-1",
    [string]$AppInstanceName = "c270-hotel-app",
    [string]$JenkinsInstanceName = "c270-jenkins",
    [string]$KeyPath = (Join-Path $HOME ".ssh\labsuser.pem"),
    [switch]$StartInstances,
    [switch]$RepairSecurityGroups,
    [switch]$RepairJenkins,
    [switch]$CheckApplication,
    [switch]$CheckJenkins,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BootstrapLocal = Join-Path $PSScriptRoot "bootstrap_jenkins.sh"
$JenkinsProbeLocal = Join-Path $PSScriptRoot "remote_jenkins_probe.sh"
$JenkinsRepairLocal = Join-Path $PSScriptRoot "remote_jenkins_repair.sh"
$AppProbeLocal = Join-Path $PSScriptRoot "remote_app_probe.sh"

function Write-Info([string]$Message) { Write-Host $Message }
function Write-Step([string]$Message) { Write-Host ""; Write-Host "==> $Message" }
function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

function Test-IPv4([string]$Value) {
    return [bool]($Value -match '^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$')
}

function Import-AcademyCredentialsFromClipboard {
    Write-Step "Loading AWS Academy credentials from Windows clipboard"
    $raw = ""
    try { $raw = Get-Clipboard -Raw } catch { Fail "Unable to read Windows clipboard." }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        Fail "Copy the complete newest AWS Academy CLI credential block to the Windows clipboard, then rerun this recovery command."
    }

    $access = $null
    $secret = $null
    $token = $null

    if ($raw -match '(?im)^\s*aws_access_key_id\s*=\s*(\S+)') { $access = $Matches[1].Trim() }
    if ($raw -match '(?im)^\s*aws_secret_access_key\s*=\s*(\S+)') { $secret = $Matches[1].Trim() }
    if ($raw -match '(?im)^\s*aws_session_token\s*=\s*(\S+)') { $token = $Matches[1].Trim() }

    if (-not $access -and $raw -match '(?im)export\s+AWS_ACCESS_KEY_ID=(\S+)') { $access = $Matches[1].Trim().Trim('"').Trim("'") }
    if (-not $secret -and $raw -match '(?im)export\s+AWS_SECRET_ACCESS_KEY=(\S+)') { $secret = $Matches[1].Trim().Trim('"').Trim("'") }
    if (-not $token -and $raw -match '(?im)export\s+AWS_SESSION_TOKEN=(\S+)') { $token = $Matches[1].Trim().Trim('"').Trim("'") }

    if ([string]::IsNullOrWhiteSpace($access) -or
        [string]::IsNullOrWhiteSpace($secret) -or
        [string]::IsNullOrWhiteSpace($token)) {
        Fail "Copy the complete newest AWS Academy CLI credential block to the Windows clipboard, then rerun this recovery command."
    }
    if ($access -notmatch '^(ASIA|AKIA)[A-Z0-9]{8,}$') {
        Fail "Clipboard access key format looks invalid. Copy the complete newest AWS Academy CLI credential block, then rerun."
    }
    if ($token.Length -le 100) {
        Fail "Clipboard session token looks incomplete. Copy the complete newest AWS Academy CLI credential block, then rerun."
    }

    $env:AWS_ACCESS_KEY_ID = $access
    $env:AWS_SECRET_ACCESS_KEY = $secret
    $env:AWS_SESSION_TOKEN = $token
    $env:AWS_REGION = $Region
    $env:AWS_DEFAULT_REGION = $Region

    $identityJson = aws sts get-caller-identity --region $Region --output json 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail "AWS STS rejected the clipboard credentials. Refresh the Learner Lab CLI block, copy it again, then rerun."
    }
    $identity = $identityJson | ConvertFrom-Json
    Write-Info ("AWS Account : {0}" -f $identity.Account)
    Write-Info ("Role ARN    : {0}" -f $identity.Arn)
    Write-Info ("Region      : {0}" -f $Region)
}

function Get-CurrentClientCidr {
    Write-Step "Discovering current client public IPv4"
    $ip = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com" -TimeoutSec 20).ToString().Trim()
    if (-not (Test-IPv4 $ip)) {
        Fail "Could not determine a valid client public IPv4 address."
    }
    $cidr = "$ip/32"
    Write-Info "Client CIDR : $cidr"
    return $cidr
}

function Get-C270Instance([string]$NameTag) {
    $query = "Reservations[].Instances[].[InstanceId,State.Name,PublicIpAddress,PrivateIpAddress,IamInstanceProfile.Arn,SecurityGroups[0].GroupId]"
    $text = aws ec2 describe-instances --region $Region `
        --filters "Name=tag:Name,Values=$NameTag" "Name=instance-state-name,Values=pending,running,stopping,stopped" `
        --query $query --output text 2>&1
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($text)) {
        Fail "No active EC2 instance found for Name=$NameTag"
    }

    $rows = @()
    foreach ($line in ($text -split "`n")) {
        $line = $line.Trim()
        if (-not $line) { continue }
        $p = $line -split "`t"
        if ($p.Count -lt 2) { continue }
        $rows += [pscustomobject]@{
            Name            = $NameTag
            InstanceId      = $p[0]
            State           = $p[1]
            PublicIp        = $(if ($p.Count -ge 3 -and $p[2] -ne "None") { $p[2] } else { "" })
            PrivateIp       = $(if ($p.Count -ge 4 -and $p[3] -ne "None") { $p[3] } else { "" })
            InstanceProfile = $(if ($p.Count -ge 5 -and $p[4] -ne "None") { $p[4] } else { "" })
            PrimarySg       = $(if ($p.Count -ge 6 -and $p[5] -ne "None") { $p[5] } else { "" })
        }
    }
    if ($rows.Count -ne 1) {
        Fail "Expected exactly one active instance for Name=$NameTag; found $($rows.Count)."
    }
    return $rows[0]
}

function Get-InstanceStatusSummary([string]$InstanceId) {
    $status = aws ec2 describe-instance-status --region $Region --instance-ids $InstanceId `
        --include-all-instances `
        --query "InstanceStatuses[0].[InstanceStatus.Status,SystemStatus.Status]" --output text 2>&1
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($status)) {
        return "unknown/unknown"
    }
    return ($status -replace "`t", "/")
}

function Start-C270InstanceIfNeeded($Inst) {
    if ($Inst.State -eq "running") { return $Inst }
    if (-not $StartInstances) {
        Fail ("Instance {0} ({1}) is {2}. Re-run with -StartInstances." -f $Inst.Name, $Inst.InstanceId, $Inst.State)
    }
    Write-Info ("Starting {0} ({1}) ..." -f $Inst.Name, $Inst.InstanceId)
    aws ec2 start-instances --region $Region --instance-ids $Inst.InstanceId | Out-Null
    aws ec2 wait instance-running --region $Region --instance-ids $Inst.InstanceId
    aws ec2 wait instance-status-ok --region $Region --instance-ids $Inst.InstanceId
    return (Get-C270Instance -NameTag $Inst.Name)
}

function Get-SecurityGroupIds([string]$InstanceId) {
    $text = aws ec2 describe-instances --region $Region --instance-ids $InstanceId `
        --query "Reservations[0].Instances[0].SecurityGroups[].GroupId" --output text
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($text)) {
        Fail "Unable to list security groups for $InstanceId"
    }
    return @(($text -split "\s+") | Where-Object { $_ -and $_ -ne "None" })
}

function Test-SgHasRule([string]$GroupId, [int]$Port, [string]$Cidr) {
    $count = aws ec2 describe-security-groups --region $Region --group-ids $GroupId `
        --query "SecurityGroups[0].IpPermissions[?FromPort==``$Port`` && ToPort==``$Port`` && IpProtocol=='tcp'].IpRanges[?CidrIp=='$Cidr'] | length(@)" `
        --output text 2>$null
    if ($LASTEXITCODE -ne 0) { return $false }
    return ([int]$count -gt 0)
}

function Ensure-ManagedIngress([string]$GroupId, [int]$Port, [string]$Cidr, [string]$Description) {
    if (Test-SgHasRule -GroupId $GroupId -Port $Port -Cidr $Cidr) {
        Write-Info ("SG {0}: TCP {1} from {2} already present" -f $GroupId, $Port, $Cidr)
        return $true
    }

    # Replace only previous managed /32 rules with the same description.
    $old = aws ec2 describe-security-groups --region $Region --group-ids $GroupId `
        --query "SecurityGroups[0].IpPermissions[?FromPort==``$Port`` && ToPort==``$Port`` && IpProtocol=='tcp'].IpRanges[?Description=='$Description'].CidrIp" `
        --output text 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($old) -and $old -ne "None") {
        foreach ($oldCidr in ($old -split "\s+")) {
            if (-not $oldCidr -or $oldCidr -eq $Cidr) { continue }
            Write-Info ("SG {0}: replacing managed TCP {1} {2} -> {3}" -f $GroupId, $Port, $oldCidr, $Cidr)
            aws ec2 revoke-security-group-ingress --region $Region --group-id $GroupId `
                --ip-permissions "IpProtocol=tcp,FromPort=$Port,ToPort=$Port,IpRanges=[{CidrIp=$oldCidr,Description=$Description}]" | Out-Null
        }
    }

    Write-Info ("SG {0}: adding TCP {1} from {2} ({3})" -f $GroupId, $Port, $Cidr, $Description)
    $err = aws ec2 authorize-security-group-ingress --region $Region --group-id $GroupId `
        --ip-permissions "IpProtocol=tcp,FromPort=$Port,ToPort=$Port,IpRanges=[{CidrIp=$Cidr,Description=$Description}]" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: could not authorize SG rule (Academy may deny). Manual Console steps:"
        Write-Host "  EC2 -> Security Groups -> $GroupId -> Edit inbound rules"
        Write-Host "  Add: TCP $Port Source $Cidr Description $Description"
        Write-Host "  AWS error: $err"
        return $false
    }
    return $true
}

function Assert-NoPublic3306([string]$GroupId) {
    $open = aws ec2 describe-security-groups --region $Region --group-ids $GroupId `
        --query "SecurityGroups[0].IpPermissions[?FromPort==``3306`` || ToPort==``3306``].IpRanges[?CidrIp=='0.0.0.0/0' || CidrIp=='::/0'] | length(@)" `
        --output text 2>$null
    if ($LASTEXITCODE -eq 0 -and [int]$open -gt 0) {
        Fail "Security group $GroupId exposes MySQL 3306 publicly. Fix in Console before continuing."
    }
    Write-Info ("SG {0}: no public 3306 rule (OK)" -f $GroupId)
}

function Test-TcpQuick([string]$HostName, [int]$Port) {
    $t = Test-NetConnection -ComputerName $HostName -Port $Port -WarningAction SilentlyContinue
    return [bool]$t.TcpTestSucceeded
}

function Get-SshBaseArgs {
    return @(
        "-o", "IdentitiesOnly=yes",
        "-o", "ConnectTimeout=15",
        "-o", "StrictHostKeyChecking=accept-new",
        "-i", $KeyPath
    )
}

function Invoke-RemoteScriptFile([string]$PublicIp, [string]$LocalScriptPath, [string]$RemoteName) {
    if (-not (Test-Path -LiteralPath $KeyPath)) {
        Fail "SSH key not found at $KeyPath"
    }
    if (-not (Test-Path -LiteralPath $LocalScriptPath)) {
        Fail "Missing remote helper script: $LocalScriptPath"
    }

    $sshBase = Get-SshBaseArgs
    $remotePath = "/tmp/$RemoteName"
    $target = "ec2-user@${PublicIp}:${remotePath}"

    $scpOut = & scp @sshBase $LocalScriptPath $target 2>&1
    if ($LASTEXITCODE -ne 0) {
        $joined = ($scpOut | Out-String)
        if ($joined -match "REMOTE HOST IDENTIFICATION HAS CHANGED") {
            Write-Info "Host key changed for $PublicIp - removing only that known_hosts entry"
            ssh-keygen -R $PublicIp | Out-Null
            $scpOut = & scp @sshBase $LocalScriptPath $target 2>&1
            if ($LASTEXITCODE -ne 0) {
                Fail ("SCP to {0} failed after host-key refresh:`n{1}" -f $PublicIp, ($scpOut | Out-String))
            }
        }
        else {
            Fail ("SCP to {0} failed:`n{1}" -f $PublicIp, $joined)
        }
    }

    $sshArgs = $sshBase + @("ec2-user@$PublicIp", "bash $remotePath")
    $out = & ssh @sshArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        $joined = ($out | Out-String)
        if ($joined -match "REMOTE HOST IDENTIFICATION HAS CHANGED") {
            Write-Info "Host key changed for $PublicIp - removing only that known_hosts entry"
            ssh-keygen -R $PublicIp | Out-Null
            $out = & ssh @sshArgs 2>&1
            if ($LASTEXITCODE -ne 0) {
                Fail ("SSH to {0} failed after host-key refresh:`n{1}" -f $PublicIp, ($out | Out-String))
            }
        }
        else {
            Fail ("SSH to {0} failed:`n{1}" -f $PublicIp, $joined)
        }
    }
    return ($out | Out-String)
}

function Repair-JenkinsHost([string]$PublicIp) {
    Write-Step "Checking Jenkins host services"
    $result = Invoke-RemoteScriptFile -PublicIp $PublicIp -LocalScriptPath $JenkinsProbeLocal -RemoteName "remote_jenkins_probe.sh"
    Write-Host $result.TrimEnd()

    $needsBootstrap = $false
    if ($result -notmatch 'JENKINS_ACTIVE=active' -or
        $result -notmatch 'DOCKER_ACTIVE=active' -or
        $result -match 'DOCKER=missing' -or
        $result -match 'INTERNAL_HTTP=000') {
        $needsBootstrap = $true
    }

    if ($RepairJenkins -or $needsBootstrap) {
        Write-Step "Applying idempotent Jenkins host repair"
        if (-not (Test-Path -LiteralPath $BootstrapLocal)) {
            Fail "Missing bootstrap script: $BootstrapLocal"
        }
        $sshBase = Get-SshBaseArgs
        & scp @sshBase $BootstrapLocal "ec2-user@${PublicIp}:/tmp/bootstrap_jenkins.sh" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Fail "Failed to copy bootstrap_jenkins.sh to Jenkins host."
        }
        $result = Invoke-RemoteScriptFile -PublicIp $PublicIp -LocalScriptPath $JenkinsRepairLocal -RemoteName "remote_jenkins_repair.sh"
        Write-Host $result.TrimEnd()
    }

    if ($result -notmatch 'INTERNAL_HTTP=(200|302|403)') {
        Fail "Jenkins internal HTTP check failed. Collect: sudo systemctl status jenkins --no-pager -l"
    }
    if ($result -match 'INSTANCE_ROLE_ARN=unavailable') {
        Write-Host "WARN: Jenkins instance role STS failed. Attach LabInstanceProfile/LabRole in EC2 Console before full deploy."
    }
}

function Check-ApplicationHost([string]$PublicIp) {
    Write-Step "Checking application host"
    $out = Invoke-RemoteScriptFile -PublicIp $PublicIp -LocalScriptPath $AppProbeLocal -RemoteName "remote_app_probe.sh"
    Write-Host $out.TrimEnd()
}

# ---------------- main ----------------
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Fail "AWS CLI not found on PATH."
}
if (-not (Test-Path -LiteralPath $KeyPath)) {
    Fail "SSH key not found at $KeyPath"
}

Write-Info "Project root : $ProjectRoot"
Write-Info "Required Jenkins branch tip: origin/ci/github-actions commit aedb66d (or later)"

Import-AcademyCredentialsFromClipboard
$clientCidr = Get-CurrentClientCidr

Write-Step "Discovering EC2 instances"
$app = Get-C270Instance -NameTag $AppInstanceName
$jenkins = Get-C270Instance -NameTag $JenkinsInstanceName
$app = Start-C270InstanceIfNeeded $app
$jenkins = Start-C270InstanceIfNeeded $jenkins

$appStatus = Get-InstanceStatusSummary $app.InstanceId
$jenkinsStatus = Get-InstanceStatusSummary $jenkins.InstanceId

Write-Info ("App     : {0} state={1} public={2} private={3} status={4}" -f $app.InstanceId, $app.State, $app.PublicIp, $app.PrivateIp, $appStatus)
Write-Info ("Jenkins : {0} state={1} public={2} private={3} status={4}" -f $jenkins.InstanceId, $jenkins.State, $jenkins.PublicIp, $jenkins.PrivateIp, $jenkinsStatus)
Write-Info ("App IAM : {0}" -f $(if ($app.InstanceProfile) { $app.InstanceProfile } else { "none" }))
Write-Info ("Jen IAM : {0}" -f $(if ($jenkins.InstanceProfile) { $jenkins.InstanceProfile } else { "none" }))

if ([string]::IsNullOrWhiteSpace($app.PublicIp) -or [string]::IsNullOrWhiteSpace($jenkins.PublicIp)) {
    Fail "One or both instances still lack a public IPv4 address."
}

Write-Step "Security group diagnosis"
$appSgs = Get-SecurityGroupIds $app.InstanceId
$jenkinsSgs = Get-SecurityGroupIds $jenkins.InstanceId
foreach ($sg in $appSgs) { Assert-NoPublic3306 $sg }
foreach ($sg in $jenkinsSgs) { Assert-NoPublic3306 $sg }

$sgOk = $true
if ($RepairSecurityGroups) {
    foreach ($sg in $appSgs) {
        if (-not (Ensure-ManagedIngress $sg 22 $clientCidr "c270-managed-ssh")) { $sgOk = $false }
        if (-not (Ensure-ManagedIngress $sg 5050 $clientCidr "c270-managed-app")) { $sgOk = $false }
    }
    foreach ($sg in $jenkinsSgs) {
        if (-not (Ensure-ManagedIngress $sg 22 $clientCidr "c270-managed-ssh")) { $sgOk = $false }
        if (-not (Ensure-ManagedIngress $sg 8080 $clientCidr "c270-managed-jenkins")) { $sgOk = $false }
    }
}
else {
    Write-Info "Skipping SG repair (pass -RepairSecurityGroups to add current /32 rules)."
}

Write-Step "Local TCP port tests"
$app22 = Test-TcpQuick $app.PublicIp 22
$app5050 = Test-TcpQuick $app.PublicIp 5050
$jen22 = Test-TcpQuick $jenkins.PublicIp 22
$jen8080 = Test-TcpQuick $jenkins.PublicIp 8080
Write-Info ("App 22/5050       : {0} / {1}" -f $app22, $app5050)
Write-Info ("Jenkins 22/8080   : {0} / {1}" -f $jen22, $jen8080)

if (-not $jen22) {
    Fail "Jenkins SSH (22) failed. Fix SG TCP 22 from $clientCidr then rerun with -RepairSecurityGroups."
}
if (-not $app22 -and $CheckApplication) {
    Write-Host "WARN: App SSH (22) failed. Fix SG TCP 22 from $clientCidr for app security group."
}

if ($CheckJenkins -or $RepairJenkins) {
    Repair-JenkinsHost -PublicIp $jenkins.PublicIp
}

if ($CheckApplication -and $app22) {
    Check-ApplicationHost -PublicIp $app.PublicIp
}

Write-Step "External Jenkins HTTP check"
$jen8080 = Test-TcpQuick $jenkins.PublicIp 8080
$jenkinsUrl = "http://$($jenkins.PublicIp):8080/"
$loginUrl = "http://$($jenkins.PublicIp):8080/login"
$extCode = "000"
try {
    $resp = Invoke-WebRequest -Uri $loginUrl -UseBasicParsing -TimeoutSec 15
    $extCode = [string]$resp.StatusCode
}
catch {
    if ($_.Exception.Response) {
        $extCode = [string][int]$_.Exception.Response.StatusCode
    }
}
Write-Info "Jenkins URL      : $jenkinsUrl"
Write-Info "External login   : HTTP $extCode"
Write-Info "Port 8080 TCP    : $jen8080"

if ($extCode -notin @("200", "302", "403") -or -not $jen8080) {
    Fail "Jenkins external login page is not reachable yet. Do not use a bookmarked old IP. Retry after SG/service repair."
}

if ($OpenBrowser) {
    Start-Process $jenkinsUrl
}

Write-Step "Recovery complete - browser-only next steps"
Write-Host ""
Write-Host "Jenkins is reachable at:"
Write-Host "  $jenkinsUrl"
Write-Host ""
Write-Host "Open:"
Write-Host "  Jenkins -> c270-hotel-management-pipeline -> Build with Parameters"
Write-Host ""
Write-Host "Dry-run parameters:"
Write-Host "  DEPLOY_TO_AWS = false"
Write-Host "  RUN_SECURITY_SCAN = true"
Write-Host "  ROLLBACK_ONLY = false"
Write-Host ""
Write-Host "Confirm checkout is aedb66d (or later on ci/github-actions)."
Write-Host "Do NOT paste AWS keys, PEM contents, or Jenkins passwords into Cursor chat."

if (-not $sgOk) { exit 2 }
exit 0
