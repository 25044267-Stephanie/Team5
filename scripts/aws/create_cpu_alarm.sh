#!/usr/bin/env bash
# Optional: create a CPUUtilization alarm (notification topic optional).
set -Eeuo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
INSTANCE_ID="${INSTANCE_ID:?Set INSTANCE_ID=i-...}"
ALARM_NAME="${ALARM_NAME:-c270-hotel-cpu-high}"
THRESHOLD="${THRESHOLD:-70}"
SNS_TOPIC_ARN="${SNS_TOPIC_ARN:-}"

ARGS=(
  --region "${AWS_REGION}"
  --alarm-name "${ALARM_NAME}"
  --alarm-description "EC2 CPUUtilization > ${THRESHOLD}% for 5 minutes"
  --namespace AWS/EC2
  --metric-name CPUUtilization
  --dimensions "Name=InstanceId,Value=${INSTANCE_ID}"
  --statistic Average
  --period 300
  --evaluation-periods 1
  --threshold "${THRESHOLD}"
  --comparison-operator GreaterThanThreshold
)

if [[ -n "${SNS_TOPIC_ARN}" ]]; then
  ARGS+=(--alarm-actions "${SNS_TOPIC_ARN}")
fi

aws cloudwatch put-metric-alarm "${ARGS[@]}"
echo "==> Alarm ${ALARM_NAME} created/updated in ${AWS_REGION}"
