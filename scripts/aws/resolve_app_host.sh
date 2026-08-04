#!/usr/bin/env bash
# Resolve the current public IPv4 of the C270 application EC2 instance.
# Prints ONLY the IPv4 address on stdout. Errors go to stderr.
# Never embeds a fixed IP or AWS credentials.
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
NAME_TAG="${C270_APP_INSTANCE_NAME:-c270-hotel-app}"

if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI is required" >&2
  exit 1
fi

if ! aws sts get-caller-identity --region "${REGION}" >/dev/null 2>&1; then
  echo "ERROR: AWS credentials missing or expired (aws sts get-caller-identity failed)." >&2
  exit 1
fi

RAW="$(aws ec2 describe-instances \
  --region "${REGION}" \
  --filters \
    "Name=tag:Name,Values=${NAME_TAG}" \
    "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].PublicIpAddress" \
  --output text)"

IPS="$(printf '%s\n' "${RAW}" | tr '\t' '\n' | awk 'NF && $0 != "None"')"
COUNT="$(printf '%s\n' "${IPS}" | awk 'NF' | wc -l | tr -d ' ')"

if [ "${COUNT}" -eq 0 ]; then
  echo "ERROR: no running EC2 instance with Name=${NAME_TAG} and a public IP in ${REGION}" >&2
  exit 1
fi

if [ "${COUNT}" -gt 1 ]; then
  echo "ERROR: multiple running instances matched Name=${NAME_TAG}; refine tags" >&2
  exit 1
fi

printf '%s\n' "${IPS}" | awk 'NF { print; exit }'
