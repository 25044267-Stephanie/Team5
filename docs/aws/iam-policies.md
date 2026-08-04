# IAM policies for EC2 + GitHub Actions (us-east-1)

Replace placeholders:

- `ACCOUNT_ID` — from `aws sts get-caller-identity`
- `ECR_REPOSITORY` — default `c270-hotel-management`
- `GITHUB_ORG_OR_USER` / `REPO` — e.g. `25044267-Stephanie` / `Team5_HotelManagement_Project`
- `OIDC_PROVIDER_ARN` — created once for `token.actions.githubusercontent.com`

Never paste long-lived access keys into the repository.

## 1. EC2 instance role (preferred)

Attach an instance profile to the Amazon Linux 2023 host.

### Trust policy (EC2)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Permissions (ECR pull + CloudWatch)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EcrPullOneRepo",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:DescribeRepositories",
        "ecr:DescribeImages"
      ],
      "Resource": "arn:aws:ecr:us-east-1:ACCOUNT_ID:repository/c270-hotel-management"
    },
    {
      "Sid": "CloudWatchAgent",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData",
        "ec2:DescribeVolumes",
        "ec2:DescribeTags",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
        "logs:DescribeLogGroups"
      ],
      "Resource": "*"
    }
  ]
}
```

Do **not** attach `AdministratorAccess` to the instance role.

## 2. GitHub Actions deploy role (OIDC — preferred)

### Trust policy (repo + main only)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "OIDC_PROVIDER_ARN"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:GITHUB_ORG_OR_USER/REPO:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

### Permissions (ECR push only)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "EcrPushOneRepo",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeRepositories",
        "ecr:DescribeImages"
      ],
      "Resource": "arn:aws:ecr:us-east-1:ACCOUNT_ID:repository/c270-hotel-management"
    }
  ]
}
```

GitHub Environment secret: `AWS_ROLE_TO_ASSUME` = role ARN.

## 3. AWS Academy fallback (when OIDC / custom IAM is blocked)

Academy Learner Lab often provides **temporary** credentials that expire with the lab session.

1. Prefer creating the EC2 instance role / ECR via Learner Lab “AWS Details” / console if the lab UI exposes roles.
2. If GitHub OIDC cannot be created:
   - Store temporary `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` only in the GitHub Environment **`production`** secrets.
   - Mark them as lab-session secrets; rotate/delete when the lab ends.
   - Never commit them; never put them in `.env` in git.
3. Document in your demo that OIDC is the production-grade design; Academy keys are a sandbox constraint.

## 4. SSH deploy secret (selected method for Academy)

This project’s deploy workflow uses **SSH** to run `scripts/aws/deploy.sh` on EC2 (SSM Run Command is often restricted in Academy).

GitHub Environment `production` secrets:

- `EC2_SSH_PRIVATE_KEY` — PEM for `ec2-user`
- `EC2_HOST` — public DNS or IP (classroom demo only)
- `EC2_USER` — usually `ec2-user`

Security group: port 22 only from your trusted IP / classroom CIDR.
