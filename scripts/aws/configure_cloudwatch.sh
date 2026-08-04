#!/usr/bin/env bash
# Install CloudWatch agent config and (re)start the agent on Amazon Linux 2023.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/c270-hotel-management}"
CW_CONFIG="${CW_CONFIG_PATH:-${APP_DIR}/cloudwatch/amazon-cloudwatch-agent.json}"
AWS_REGION="${AWS_REGION:-us-east-1}"

if ! command -v amazon-cloudwatch-agent-ctl >/dev/null 2>&1; then
  echo "ERROR: amazon-cloudwatch-agent-ctl not found. Run bootstrap_ec2.sh first." >&2
  exit 1
fi

if [[ ! -f "${CW_CONFIG}" ]]; then
  echo "ERROR: CloudWatch config not found at ${CW_CONFIG}" >&2
  exit 1
fi

echo "==> Installing agent config from ${CW_CONFIG}"
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c "file:${CW_CONFIG}" \
  -s

echo "==> Agent status:"
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -m ec2 -a status || true

cat <<EOF

CloudWatch verification (console, region ${AWS_REGION}):
1. CloudWatch → Log groups → /c270/hotel/app and /c270/hotel/system
2. CloudWatch → Metrics → CWAgent (CPU, mem, disk)
3. Create alarm example (CLI, optional email omitted):

   aws cloudwatch put-metric-alarm \\
     --region ${AWS_REGION} \\
     --alarm-name c270-hotel-cpu-high \\
     --alarm-description "EC2 CPU > 70% for 5 minutes" \\
     --namespace AWS/EC2 \\
     --metric-name CPUUtilization \\
     --dimensions Name=InstanceId,Value=i-YOUR_INSTANCE_ID \\
     --statistic Average \\
     --period 300 \\
     --evaluation-periods 1 \\
     --threshold 70 \\
     --comparison-operator GreaterThanThreshold

Or StatusCheckFailed >= 1 for instance health.
EOF
