# Infrastructure Developer Guide

This guide explains the infrastructure layout, module outputs, deployment verification, and CI/CD configuration for developers working on LLM Tracer.

## Directory Structure

```
infrastructure/
├── bootstrap/                 # One-time setup (run with admin credentials)
│   └── main.tf
├── modules/                   # Reusable Terraform modules
│   ├── dynamodb/             # DynamoDB tables (traces, spans)
│   ├── lambda/               # Lambda function + Function URL
│   └── monitoring/           # CloudWatch alarms + Budget alerts
├── environments/             # Environment-specific configurations
│   ├── dev/                  # Development environment
│   └── prod/                 # Production environment
├── basic_deployment_test.py  # Quick manual verification script
├── backend_config.txt        # Bootstrap output reference
└── justfile                  # Deployment automation recipes
```

### Execution Order

1. **bootstrap/** - Run once per AWS account. Creates foundational resources that other modules depend on.
2. **modules/** - Reusable components, not applied directly.
3. **environments/{dev,prod}/** - Environment-specific deployments that compose modules.

### AWS Roles

To work with AWS resources, you normally should never use root user for security reasons. So I recommend 2 IAM role creations as described below:

#### IAM User Setup

Before deploying infrastructure, you need two types of IAM users with different permission levels. Never use the root user for security reasons.

**Step 1: Create a Privileged Admin User (for Bootstrap Only)**

Create a privileged IAM user named admin for running bootstrap operations. This user can create IAM roles, S3 buckets, and other foundational resources.

This admin user is reusable across multiple projects. You can attach additional policies in the future for other AWS services and projects as needed.

**Creating the Admin User:**

1. Go to AWS Console → IAM → Users → Create user
2. User name: admin
3. Select AWS credential type: Check "Access key - Programmatic access" / this is needed for AWS CLI
4. Set permissions: Click "Attach policies directly"
5. Select policy: AdministratorAccess
6. Review and create user
7. Save credentials: Download or copy the Access Key ID and Secret Access Key (you won't see the secret again)

**Configure AWS CLI with Admin Credentials:**

`aws configure --profile admin` 
- AWS Access Key ID: `<your-access-key>`
- AWS Secret Access Key: `<your-secret-key>`
- Default region name: `eu-central-1`
- Default output format: `json`

**When to Use Admin:**

- Running just bootstrap (one-time account setup)
- Creating or modifying IAM roles
- Setting up new projects that require IAM resources

**WARNING:** Never use the admin user for direct resource deployments such as deploying DynamoDB tables, Lambda functions, or API Gateways.

**Why is this critical?**

1. Blast radius: Admin credentials can modify or delete ANY resource in your AWS account. A misconfigured Terraform file, typo, or accidental terraform destroy could wipe out unrelated production systems, databases, or other projects entirely.
2. Credential exposure risk: If admin credentials are used in CI/CD pipelines, stored in .env files, or shared among team members, a single leak gives attackers full account access—not just to this project, but to everything.
3. No guardrails: Admin bypasses all permission boundaries. You could accidentally create expensive resources (GPU instances, large databases), modify billing settings, or delete audit logs.
4. Audit trail confusion: When every action uses the same admin user, you lose visibility into what was deployed by whom, making incident investigation and compliance audits difficult.
5. Principle of least privilege: Security best practice dictates that any credential should have only the minimum permissions required for its task. Deployment needs lambda:* and dynamodb:*—not iam:CreateUser or organizations:*.

Use admin only for bootstrap, then immediately switch to the deployment user for all subsequent operations.

---

**Step 2: Create a Least-Privileged Deployment User**

For all environment deployments (dev, prod), create a restricted IAM user that can only manage the specific resources needed for this project.

**Creating the Deployment User:**

1. Go to AWS Console → IAM → Policies → Create policy
2. Select JSON tab and paste the following policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "CoreServicesAccess",
        "Effect": "Allow",
        "Action": [
          "dynamodb:*",
          "lambda:*",
          "s3:*",
          "logs:*",
          "cloudwatch:*",
          "budgets:*",
          "apigateway:*"
        ],
        "Resource": "*"
      },
      {
        "Sid": "PassRoleOnly",
        "Effect": "Allow",
        "Action": "iam:PassRole",
        "Resource": "arn:aws:iam::*:role/llm-tracer-*"
      },
      {
        "Sid": "ViewIAMOnly",
        "Effect": "Allow",
        "Action": [
          "iam:List*",
          "iam:Get*"
        ],
        "Resource": "*"
      }
    ]
}
```

3. Name the policy: LLMTracerDeploymentPolicy
4. Create the policy
5. Go to IAM → Users → Create user
6. User name: llm-tracer-dev
7. Select AWS credential type: Check "Access key - Programmatic access"
8. Set permissions: Click "Attach policies directly" → Search and select LLMTracerDeploymentPolicy
9. Review and create user
10. Save credentials: Download or copy the Access Key ID and Secret Access Key

Configure AWS CLI with Deployment Credentials:

`aws configure --profile llm-tracer`
- AWS Access Key ID: `<deployment-user-access-key>`
- AWS Secret Access Key: `<deployment-user-secret-key>`
- Default region name: `eu-central-1`
- Default output format: `json`

Key Security Features of This Policy:

  | Permission                           | What It Allows                                  | What It Prevents                             |
  |--------------------------------------|-------------------------------------------------|----------------------------------------------|
  | iam:PassRole on llm-tracer-*         | Assign the pre-created Lambda role              | Creating new roles or escalating privileges  |
  | iam:List*, iam:Get*                  | View IAM resources (needed for Terraform state) | Modifying users, roles, or policies          |
  | No iam:Create*                       | —                                               | Cannot create IAM users, roles, or policies  |
  | No sts:AssumeRole on arbitrary roles | —                                               | Cannot assume other roles to escalate access |

When to Use Deployment User:

- Running just deploy-dev or just deploy-prod
- All CI/CD pipeline operations (GitHub Actions)
- Day-to-day infrastructure changes and updates




## Module Outputs and Dependencies

### 1. Bootstrap Module (`bootstrap/main.tf`)

The bootstrap module creates account-level resources required before any environment deployment.

**Creates:**
- S3 bucket for Terraform state storage
- DynamoDB table for state locking
- Lambda execution IAM role (with DynamoDB permissions)

**Key Outputs:**

| Output | Description | Used By |
|--------|-------------|---------|
| `s3_bucket_name` | Terraform state bucket | `environments/*/backend.hcl` |
| `dynamodb_table_name` | State lock table | `environments/*/backend.hcl` |
| `lambda_role_arn` | Pre-created Lambda role ARN | `environments/*/terraform.tfvars` |
| `account_id` | AWS Account ID | Resource naming convention |
| `name_prefix` | `{project}-{account_id}` | Consistent resource naming |

**Why bootstrap exists:** The Lambda role is pre-created here so that environment deployments only need `iam:PassRole` permission, not `iam:CreateRole`. This follows least-privilege principles for the deployment user. This is to insure that the deployment user (a different IAM role with least amount of privileges) can not damage or blow up the costs by accidently destroying or creating resources.

---

### 2. DynamoDB Module (`modules/dynamodb/`)

**Creates:**
- `traces` table (hash key: `trace_id`, GSI on `project_id` + `start_time`)
- `spans` table (hash key: `span_id`, GSI on `trace_id`)

**Outputs:**

| Output | Description | Used By |
|--------|-------------|---------|
| `traces_table_name` | Full table name | Lambda environment variables |
| `traces_table_arn` | Table ARN | IAM policies (if needed) |
| `spans_table_name` | Full table name | Lambda environment variables |
| `spans_table_arn` | Table ARN | IAM policies (if needed) |

**Naming Convention:**
```
{project_name}-{account_id}-{environment}-{resource}
Example: llm-tracer-882760960155-dev-traces
```

---

### 3. Lambda Module (`modules/lambda/`)

**Creates:**
- Lambda function (Python 3.12 runtime)
- Lambda Function URL (public, auth handled in application)
- CloudWatch Log Group

**Outputs:**

| Output | Description | Used By |
|--------|-------------|---------|
| `function_name` | Lambda function name | Monitoring module, CI/CD |
| `function_arn` | Lambda function ARN | - |
| `function_url` | Public HTTPS endpoint | Client configuration, `.env` |

**Dependencies:**
- Requires `lambda_role_arn` from bootstrap
- Requires `traces_table_name` and `spans_table_name` from DynamoDB module

---

### 4. Monitoring Module (`modules/monitoring/`)

**Creates:**
- AWS Budget alert (cost monitoring)
- CloudWatch alarms for Lambda errors (optional)
- CloudWatch alarms for DynamoDB throttling (optional)

**Dependencies:**
- Requires `lambda_function_name` from Lambda module
- Requires `traces_table_name` from DynamoDB module

---

### 5. Environment Outputs (`environments/{dev,prod}/outputs.tf`)

After deployment, the environment outputs provide everything needed to configure clients:

| Output | Description | Where to Use |
|--------|-------------|--------------|
| `api_url` | Lambda Function URL | `.env` → `TRACER_URL` |
| `traces_table_name` | DynamoDB traces table | `.env`, GitHub vars |
| `spans_table_name` | DynamoDB spans table | `.env`, GitHub vars |
| `lambda_function_name` | Lambda function name | Logs, debugging |
| `configuration` | Ready-to-copy `.env` block | Local development |

Run `just output-dev` or `just output-prod` to view these outputs.

---

## Deployment Verification

### Quick Manual Test: `basic_deployment_test.py`

Located at `infrastructure/basic_deployment_test.py`, this script provides a minimal end-to-end verification:

```bash
# From project root (ensure .env is configured)
cd infrastructure
python basic_deployment_test.py
```

**What it tests:**
1. Create a trace via POST `/api/traces`
2. Add a span via POST `/api/traces/{trace_id}/spans`
3. Complete the span via PATCH `/api/spans/{span_id}/complete`
4. Complete the trace via PATCH `/api/traces/{trace_id}/complete`

**Required `.env` variables:**
```bash
# Client-side: Where to send traces
TRACER_URL=https://xxx.lambda-url.eu-central-1.on.aws/

# Client-side: API key to authenticate (must match one of server's API_KEYS)
API_KEY=project-dev
```

This script is intentionally simple for quick manual verification after deployment.

---

### Automated Deployment Tests: `service/tests/deployment/`

The `service/tests/deployment/` directory (run via CI/CD) serves a different purpose:

| Aspect | `basic_deployment_test.py` | `service/tests/deployment/` |
|--------|---------------------------|----------------------------|
| **Purpose** | Quick sanity check | Comprehensive regression testing |
| **When to use** | After manual deployment | Automated CI/CD pipeline |
| **Scope** | 4 API calls (happy path) | Exhaustive API coverage |
| **Assertions** | Print output verification | Full pytest assertions |
| **Data cleanup** | None (test data persists) | Should clean up test data |

Use `basic_deployment_test.py` for:
- First-time deployment verification
- Quick smoke test after infrastructure changes
- Learning how the API works

Use `service/tests/deployment/` for:
- CI/CD pipelines
- Pre-release verification
- Catching regressions across API endpoints

---

## GitHub Actions CI/CD Configuration

The workflow `.github/workflows/deployment-tests.yml` requires specific GitHub configuration.

### Required GitHub Secrets (Repository → Settings → Secrets)

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | Deployment user access key |
| `AWS_SECRET_ACCESS_KEY` | Deployment user secret key |
| `API_KEY` | Client-side: API key for tests to authenticate (must match one of server's `API_KEYS`) |

### Required GitHub Environment Variables

Create environments `dev` and `prod` under Repository → Settings → Environments, then add:

| Variable | Source | Example Value |
|----------|--------|---------------|
| `API_BASE_URL` | `terraform output api_url` | `https://xxx.lambda-url.eu-central-1.on.aws/` |
| `DYNAMODB_TRACES_TABLE` | `terraform output traces_table_name` | `llm-tracer-882760960155-dev-traces` |
| `DYNAMODB_SPANS_TABLE` | `terraform output spans_table_name` | `llm-tracer-882760960155-dev-spans` |

**After each deployment**, update these variables with the new Terraform outputs:

```bash
# Get values to copy to GitHub
cd infrastructure
just output-dev  # or output-prod
```

---

## Advanced

### Resource Naming Convention

All resources follow the pattern:
```
{project_name}-{account_id}-{environment}-{resource}
```

This ensures:
- Global uniqueness (account ID prevents collisions)
- Easy identification of environment
- Consistent IAM policy patterns (wildcard on `{project}-{account_id}-*`)

The Lambda role in bootstrap grants DynamoDB access to all tables matching `llm-tracer-{account_id}-*`, so environment deployments automatically have correct permissions.

### Lambda Role Separation

The Lambda execution role is created in bootstrap, not in environment modules. This is intentional:

1. **Least privilege**: Deployment user only needs `iam:PassRole`, not `iam:CreateRole`
2. **Consistency**: Same role across environments (simpler IAM auditing)
3. **Bootstrap isolation**: Re-running environment deployments won't affect IAM

If you need environment-specific permissions, modify the bootstrap role policy or create a new policy attachment in the environment module.

### DynamoDB Table Name Override

By default, table names are auto-generated. To use custom names:

```hcl
# In environments/dev/terraform.tfvars
traces_table_name = "my-custom-traces-table"
spans_table_name  = "my-custom-spans-table"
```

This is useful when migrating existing tables or sharing tables across deployments.

### Lambda Function URL vs API Gateway

This project uses Lambda Function URLs instead of API Gateway:

- **Simpler**: No additional resources to manage
- **Cost-effective**: No API Gateway charges
- **Trade-off**: No built-in request validation, rate limiting, or API keys at gateway level

Authentication is handled in the application layer via `X-API-Key` header validation.

### Point-in-Time Recovery (PITR)

PITR is disabled by default for dev (`enable_pitr = false`) but should be enabled for prod:

```hcl
# In environments/prod/main.tf
module "dynamodb" {
  # ...
  enable_pitr = true  # Enable for production data protection
}
```

### Monitoring Toggle Flags

The monitoring module supports toggling features:

```hcl
module "monitoring" {
  enable_cost_alerts     = true   # Budget notifications
  enable_error_alerts    = false  # Lambda error alarms (noisy for dev)
  enable_dynamodb_alerts = false  # Throttle alarms (noisy for dev)
}
```

Enable all alerts for production environments.

### State Management

Terraform state is stored in S3 with DynamoDB locking:
- State bucket: `{project}-{account_id}-terraform-state`
- Lock table: `{project}-{account_id}-terraform-locks`
- State key: `{environment}/terraform.tfstate`

Never manually edit state files. Use `terraform state` commands if state manipulation is needed.

### Justfile Recipes Reference

| Recipe | Description |
|--------|-------------|
| `just bootstrap` | Initialize account-level resources |
| `just setup-dev` | Build Lambda + create tfvars + init |
| `just deploy-dev` | Full deployment (init + apply) |
| `just apply-dev` | Apply changes only (skip init) |
| `just output-dev` | Show deployment outputs |
| `just destroy-dev` | Tear down dev environment |
| `just clean` | Remove local Terraform files |

Replace `-dev` with `-prod` for production commands.
