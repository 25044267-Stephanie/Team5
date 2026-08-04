#!/usr/bin/env bash
# Create (or reuse) the private ECR repository for the hotel app image.
#
# WHY: Academy labs are wiped between sessions — this script is idempotent so
# a student can recreate ECR in us-east-1 without hardcoding an account ID.
set -Eeuo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-c270-hotel-management}"

echo "==> Region: ${AWS_REGION}"
echo "==> Repository: ${ECR_REPOSITORY}"

if aws ecr describe-repositories --repository-names "${ECR_REPOSITORY}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  echo "==> Repository already exists (no change)."
else
  echo "==> Creating repository..."
  aws ecr create-repository \
    --repository-name "${ECR_REPOSITORY}" \
    --region "${AWS_REGION}" \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability IMMUTABLE \
    --encryption-configuration encryptionType=AES256 \
    >/dev/null
  echo "==> Repository created with scan-on-push and IMMUTABLE tags."
fi

URI="$(aws ecr describe-repositories \
  --repository-names "${ECR_REPOSITORY}" \
  --region "${AWS_REGION}" \
  --query 'repositories[0].repositoryUri' \
  --output text)"

echo "==> ECR repository URI: ${URI}"
echo "==> Example image tag: ${URI}:<git-sha>"
