<#
.SYNOPSIS
  Discover the current C270 application EC2 public IP after an AWS Academy restart.

.DESCRIPTION
  Uses AWS CLI to find exactly one instance (by InstanceId or Name tag),
  optionally starts it, polls SSH/5050, and writes the gitignored inventory
  ansible/hosts.ini. Never prints credentials or PEM contents.
#>
[CmdletBinding()]
param(
    [string]$Region = "us-east-1",
    [string]$InstanceName = "c270-hotel-app",
    [string]$InstanceId = "",
    [string]$KeyPath = (Join-Path $HOME ".ssh\labsuser.pem"),
    [switch]$StartInstance,
    [switch]$OpenBrowser,
    [switch]$SkipAnsibleInventory
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$InventoryPath = Join-Path $ProjectRoot "ansible\hosts.ini"
$WslProjectPath = "/mnt/c/Users/steph/Downloads/FA FINAL/FA FINAL/C270_Hotel_Management_Feeback_Ver"
$WslKeyPath = "/mnt/c/Users/steph/.ssh/labsuser.pem"

function Write-Info([string]$Message) { Write-Host $Message }
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
    Fail "AWS credentials missing or expired. Start the AWS Academy Learner Lab and refresh temporary credentials, then re-run this script."
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
    Fail "No EC2 instance found for Name=$InstanceName InstanceId=$InstanceId"
}

$matches = @()
foreach ($line in ($rows -split "`n")) {
    $line = $line.Trim()
    if (-not $line) { continue }
    $parts = $line -split "`t"
    if ($parts.Count -lt 2) { continue }
    $matches += [pscustomobject]@{
        InstanceId    = $parts[0]
        State         = $parts[1]
        PublicIp      = $(if ($parts.Count -ge 3 -and $parts[2] -ne "None") { $parts[2] } else { "" })
        PublicDnsName = $(if ($parts.Count -ge 4 -and $parts[3] -ne "None") { $parts[3] } else { "" })
    }
}
if ($matches.Count -ne 1) {
    Fail "Expected exactly one matching instance; found $($matches.Count)."
}

$inst = $matches[0]
$InstanceId = $inst.InstanceId
$state = $inst.State
$publicIp = $inst.PublicIp

if ($state -eq "stopped") {
    if (-not $StartInstance) {
        Fail "Instance $InstanceId is stopped. Re-run with -StartInstance to start it."
    }
    Write-Info "==> Starting $InstanceId ..."
    aws ec2 start-instances --region $Region --instance-ids $InstanceId | Out-Null
    aws ec2 wait instance-running --region $Region --instance-ids $InstanceId
    aws ec2 wait instance-status-ok --region $Region --instance-ids $InstanceId
    $publicIp = (aws ec2 describe-instances --region $Region --instance-ids $InstanceId `
        --query "Reservations[0].Instances[0].PublicIpAddress" --output text).Trim()
    $state = "running"
}

if ([string]::IsNullOrWhiteSpace($publicIp) -or $publicIp -eq "None") {
    Fail "Instance $InstanceId has no public IPv4 yet."
}

function Test-TcpPort([string]$Ip, [int]$Port, [int]$Attempts = 20, [int]$DelaySec = 15) {
    for ($i = 1; $i -le $Attempts; $i++) {
        $t = Test-NetConnection -ComputerName $Ip -Port $Port -WarningAction SilentlyContinue
        Write-Info ("  port {0} attempt {1}/{2}: {3}" -f $Port, $i, $Attempts, $t.TcpTestSucceeded)
        if ($t.TcpTestSucceeded) { return $true }
        Start-Sleep -Seconds $DelaySec
    }
    return $false
}

Write-Info "==> Polling SSH (22) on $publicIp ..."
$sshReady = Test-TcpPort -Ip $publicIp -Port 22
if (-not $sshReady) {
    Write-Info @"
SSH port 22 is not reachable.
Manual fix (do not automate security-group edits):
  AWS Console → EC2 → Instances → $InstanceName → Security → inbound rules
  → SSH (22) → Source: My IP → Save
"@
    Fail "SSH port 22 unavailable on $publicIp"
}

Write-Info "==> Polling app (5050) on $publicIp ..."
$appReady = Test-TcpPort -Ip $publicIp -Port 5050 -Attempts 12 -DelaySec 10
if (-not $appReady) {
    Write-Info @"
Port 5050 is not reachable.
Manual fix:
  AWS Console → EC2 → Security group → Custom TCP 5050 → Source: My IP → Save
"@
}

if (-not $SkipAnsibleInventory) {
    $inventory = @"
[hotel_app]
$publicIp

[hotel_app:vars]
ansible_user=ec2-user
ansible_ssh_private_key_file=$WslKeyPath
ansible_python_interpreter=/usr/bin/python3
"@
    $invDir = Split-Path -Parent $InventoryPath
    if (-not (Test-Path -LiteralPath $invDir)) {
        New-Item -ItemType Directory -Path $invDir | Out-Null
    }
    Set-Content -LiteralPath $InventoryPath -Value $inventory -Encoding ascii
    Write-Info "==> Wrote ignored inventory: ansible/hosts.ini"
}

$siteUrl = "http://${publicIp}:5050"
$healthUrl = "http://${publicIp}:5050/healthz"
$sshCmd = "ssh -o IdentitiesOnly=yes -i `"$KeyPath`" ec2-user@$publicIp"

Write-Info ""
Write-Info "InstanceId : $InstanceId"
Write-Info "State      : $state"
Write-Info "Public IP  : $publicIp"
Write-Info "Website    : $siteUrl"
Write-Info "Health URL : $healthUrl"
Write-Info "SSH        : $sshCmd"
Write-Info "WSL path   : $WslProjectPath"
Write-Info "SSH ready  : $sshReady"
Write-Info "App:5050   : $appReady"

if ($OpenBrowser -and $appReady) {
    Start-Process $siteUrl
}

if (-not $appReady) { exit 2 }
exit 0
