<#
.SYNOPSIS
  Discover the current C270 Jenkins EC2 public IP after an AWS Academy restart.

.DESCRIPTION
  Finds exactly one instance tagged Name=c270-jenkins, optionally starts it,
  polls SSH/8080, and prints the Jenkins URL. Never embeds a fixed IP or credentials.
#>
[CmdletBinding()]
param(
    [string]$Region = "us-east-1",
    [string]$InstanceName = "c270-jenkins",
    [string]$InstanceId = "",
    [string]$KeyPath = (Join-Path $HOME ".ssh\labsuser.pem"),
    [switch]$StartInstance,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Fail "AWS CLI not found on PATH."
}
if (-not (Test-Path -LiteralPath $KeyPath)) {
    Fail "SSH key not found at $KeyPath"
}

try {
    $null = aws sts get-caller-identity --region $Region 2>&1
    if ($LASTEXITCODE -ne 0) { throw "sts failed" }
}
catch {
    Fail "AWS credentials missing or expired. Refresh AWS Academy CLI credentials, then re-run."
}

$query = "Reservations[].Instances[].[InstanceId,State.Name,PublicIpAddress,PublicDnsName]"
if ($InstanceId) {
    $rows = aws ec2 describe-instances --region $Region --instance-ids $InstanceId --query $query --output text
}
else {
    $rows = aws ec2 describe-instances --region $Region `
        --filters "Name=tag:Name,Values=$InstanceName" `
        --query $query --output text
}
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($rows)) {
    Fail "No EC2 instance found for Name=$InstanceName. Create c270-jenkins in AWS Console first."
}

$matches = @()
foreach ($line in ($rows -split "`n")) {
    $line = $line.Trim()
    if (-not $line) { continue }
    $parts = $line -split "`t"
    if ($parts.Count -lt 2) { continue }
    $matches += [pscustomobject]@{
        InstanceId = $parts[0]
        State      = $parts[1]
        PublicIp   = $(if ($parts.Count -ge 3 -and $parts[2] -ne "None") { $parts[2] } else { "" })
    }
}
if ($matches.Count -ne 1) {
    Fail "Expected exactly one matching Jenkins instance; found $($matches.Count)."
}

$inst = $matches[0]
$InstanceId = $inst.InstanceId
$state = $inst.State
$publicIp = $inst.PublicIp

if ($state -eq "stopped") {
    if (-not $StartInstance) {
        Fail "Instance $InstanceId is stopped. Re-run with -StartInstance to start it."
    }
    Write-Host "Starting $InstanceId ..."
    aws ec2 start-instances --region $Region --instance-ids $InstanceId | Out-Null
    aws ec2 wait instance-running --region $Region --instance-ids $InstanceId
    aws ec2 wait instance-status-ok --region $Region --instance-ids $InstanceId
    $publicIp = aws ec2 describe-instances --region $Region --instance-ids $InstanceId `
        --query "Reservations[0].Instances[0].PublicIpAddress" --output text
}

if ([string]::IsNullOrWhiteSpace($publicIp) -or $publicIp -eq "None") {
    Fail "Instance $InstanceId has no public IPv4 address."
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSec = 3) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSec))
        if (-not $ok) { $client.Close(); return $false }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    }
    catch { return $false }
}

$sshReady = $false
$httpReady = $false
for ($i = 1; $i -le 36; $i++) {
    if (-not $sshReady) { $sshReady = Test-TcpPort $publicIp 22 }
    if (-not $httpReady) { $httpReady = Test-TcpPort $publicIp 8080 }
    if ($sshReady -and $httpReady) { break }
    Start-Sleep -Seconds 5
}

$jenkinsUrl = "http://${publicIp}:8080/"
Write-Host ""
Write-Host "Jenkins instance ID : $InstanceId"
Write-Host "State               : $state"
Write-Host "Public IP           : $publicIp"
Write-Host "Jenkins URL         : $jenkinsUrl"
Write-Host "SSH                 : ssh -i `"$KeyPath`" ec2-user@$publicIp"
Write-Host "Port 22 ready       : $sshReady"
Write-Host "Port 8080 ready     : $httpReady"
Write-Host ""
Write-Host "Initial password (on the instance, do not paste into chat/Git):"
Write-Host "  sudo cat /var/lib/jenkins/secrets/initialAdminPassword"
Write-Host ""
if (-not $sshReady) {
    Write-Host "SSH blocked. In security group c270-jenkins-sg allow TCP 22 from My IP."
}
if (-not $httpReady) {
    Write-Host "Jenkins UI blocked. In security group c270-jenkins-sg allow TCP 8080 from My IP."
}

if ($OpenBrowser -and $httpReady) {
    Start-Process $jenkinsUrl
}

if (-not $sshReady -or -not $httpReady) {
    exit 2
}
exit 0
