# LLM Tracer

**Self-hosted LLM observability that costs you only what you actually use.**

Tired of paying $20-100+/month for LLM tracing platforms when you're just experimenting? LLM Tracer gives you production-grade observability on your own AWS infrastructure, where you only pay for actual compute and storage (~$2-5/month for most use cases).

## Why LLM Tracer?

| Platform | Monthly Cost | What You Pay For |
|----------|--------------|------------------|
| Popular paid services, etc. | $20-100+ | Seats, data retention, features |
| **LLM Tracer** | **~$2-5** | Only DynamoDB storage + Lambda invocations |

Perfect for:
- **Data Scientists** running experiments and comparing prompts
- **ML Engineers** debugging agent pipelines in development
- **Solo developers** who want observability without monthly SaaS bills
- **Teams** who prefer owning their trace data

## Quick Start (5 minutes)

### Option 1: Local Development

```bash
# Clone and start
git clone https://github.com/indinewton/llm-tracer.git
cd llm-tracer/service

# Start local DynamoDB + API server
docker-compose up -d

# Verify it's running
curl http://localhost:8001/health
```

### Option 2: Deploy to AWS

Requires: [just](https://github.com/casey/just#installation) command runner (`brew install just`)

```bash
cd infrastructure

# 1. Bootstrap (one-time) - creates S3 state bucket, IAM roles
just bootstrap

# 2. Setup dev environment (builds Lambda, generates configs, initializes Terraform)
just setup-dev

# 3. Review terraform.tfvars, then deploy
just plan-dev
just apply-dev

# 4. Get your API URL
just output-dev
```

## Using the Client

### Installation

```bash
pip install ./client
# or add to your requirements.txt/pyproject.toml
```

### Basic Usage (Async - Recommended)

```python
from llm_tracer import TracerClient

async with TracerClient(
    base_url="http://localhost:8001",  # or your Lambda URL
    api_key="project-dev"
) as tracer:

    async with tracer.trace("my-agent-run") as trace:

        async with trace.span("llm-call", "llm", model="gpt-4") as span:
            response = await openai.chat.completions.create(...)
            span.set_output(
                output_data={"response": response.choices[0].message.content},
                tokens_input=response.usage.prompt_tokens,
                tokens_output=response.usage.completion_tokens,
            )

        trace.set_output("Agent completed successfully")
```

### Jupyter Notebooks / Scripts (Sync)

```python
from llm_tracer import SyncTracerClient

tracer = SyncTracerClient(api_key="project-dev")

with tracer.trace("experiment-v1") as trace:
    with trace.span("gpt-4-call", "llm", model="gpt-4") as span:
        response = openai.chat.completions.create(...)
        span.set_output(
            output_data={"content": response.choices[0].message.content},
            tokens_input=response.usage.prompt_tokens,
            tokens_output=response.usage.completion_tokens,
        )

tracer.close()
```

### Environment Variables

```bash
TRACER_URL=http://localhost:8001      # or your Lambda URL
TRACER_API_KEY=project-dev            # format: project-{project_id}
TRACING_ENABLED=true                  # set to "false" to disable
```

## Architecture

```
┌──────────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Your App       │────>│   LLM Tracer    │────>│   DynamoDB   │
│   (with client)  │     │   (FastAPI)     │     │   (storage)  │
└──────────────────┘     └─────────────────┘     └──────────────┘
                                │
                                │ Runs on:
                         ┌──────┴──────┐
                         │   Lambda    │  <-- Serverless, pay-per-use
                         │   or Docker │  <-- Local development
                         └─────────────┘
```

**Key Design Decisions:**
- **DynamoDB** - Pay-per-request pricing, auto-scales to zero
- **Lambda** - No idle costs, scales automatically
- **90-day TTL** - Traces auto-delete (configurable)
- **API Key auth** - Multi-project isolation with `project-{id}` format

## Project Structure

```
llm-tracer/
├── client/                 # Python client library
│   └── llm_tracer/
│       └── client.py       # TracerClient, SyncTracerClient
├── service/                # FastAPI backend
│   ├── src/
│   │   ├── server.py       # API endpoints + built-in dashboard
│   │   ├── storage_dynamodb.py
│   │   └── models.py
│   ├── scripts/
│   │   └── build_lambda_package.sh
│   ├── Dockerfile
│   └── docker-compose.yml
├── infrastructure/         # Terraform IaC
│   ├── justfile            # Task runner (just --list for commands)
│   ├── bootstrap/          # One-time setup (S3 state, IAM roles)
│   ├── modules/            # DynamoDB, Lambda, Monitoring
│   └── environments/       # dev/, prod/ (with backend.hcl.example)
└── examples/               # Usage examples
```

## Features

- **Traces & Spans** - Hierarchical structure for complex agent workflows
- **Nested Spans** - Track tool calls, LLM calls, and sub-operations
- **Token Tracking** - Input/output tokens and cost per span
- **Built-in Dashboard** - View traces at `/dashboard` (no extra setup)
- **Multi-project** - Isolate traces by project with API keys
- **Rate Limiting** - Configurable per-project limits
- **Auto-cleanup** - TTL-based expiration (default 90 days)

## Dashboard

Access the built-in dashboard at `http://localhost:8001/dashboard` (or your Lambda URL + `/dashboard`).

Features:
- View recent traces with timing and token counts
- Drill into individual traces to see span hierarchy
- Filter by project
- No additional frontend deployment needed

## AWS Costs Breakdown

| Resource | Free Tier | After Free Tier |
|----------|-----------|-----------------|
| Lambda | 1M requests/month | $0.20 per 1M requests |
| DynamoDB | 25 GB storage | $0.25 per GB |
| DynamoDB | 25 WCU/RCU | Pay-per-request (~$1.25/M writes) |

**Realistic monthly cost for most users: $2-5**

## Configuration

### Server-side Environment Variables

These variables configure the LLM Tracer service (FastAPI backend).

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEYS` | `project-dev` | Comma-separated valid API keys the server accepts |
| `API_KEY_REQUIRED` | `true` | Require API key authentication |
| `RATE_LIMIT_RPM` | `60` | Requests per minute limit |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `DYNAMODB_TRACES_TABLE` | - | DynamoDB table for traces |
| `DYNAMODB_SPANS_TABLE` | - | DynamoDB table for spans |

### Client-side Environment Variables

These variables configure the TracerClient (Python SDK) that sends traces to the server.

| Variable | Default | Description |
|----------|---------|-------------|
| `TRACER_URL` | `http://localhost:8001` | LLM Tracer service URL |
| `TRACER_API_KEY` | - | API key to authenticate (must match one in server's `API_KEYS`) |
| `TRACER_PROJECT_ID` | - | Project identifier (auto-derived from API key if not set) |
| `TRACING_ENABLED` | `true` | Set to `false` to disable tracing |

## Development

### Running Tests

```bash
# Service tests
cd service
pip install -e ".[dev]"
pytest

# Client tests
cd client
pip install -e ".[dev]"
pytest
```

### Local Development with Docker

```bash
cd service
docker-compose up -d

# View logs
docker-compose logs -f service

# Stop
docker-compose down
```

## Deployment Guide

### Prerequisites

- AWS CLI configured (`aws configure`)
- Terraform >= 1.5.0
- [just](https://github.com/casey/just#installation) command runner
- Docker (for building Lambda package)

### Step-by-Step Deployment

```bash
cd infrastructure

# See all available commands
just --list

# 1. Bootstrap (one-time) - creates S3 state bucket, DynamoDB lock table, IAM roles
just bootstrap

# 2. Full setup for dev (builds Lambda, generates backend.hcl from bootstrap outputs, creates tfvars)
just setup-dev

# 3. Review and update terraform.tfvars (especially alert_emails)
# Then plan and apply
just plan-dev
just apply-dev

# 4. Get your API URL and other outputs
just output-dev
```

### Deploy to Production

```bash
cd infrastructure
just setup-prod
# Review environments/prod/terraform.tfvars
just plan-prod
just apply-prod
```

### Available Just Commands

| Command | Description |
|---------|-------------|
| `just bootstrap` | Initialize bootstrap (S3, IAM roles) |
| `just setup-dev` | Full dev setup (build + init) |
| `just setup-prod` | Full prod setup (build + init) |
| `just init-dev` | Generate backend.hcl and terraform init |
| `just plan-dev` | Terraform plan for dev |
| `just apply-dev` | Terraform apply for dev |
| `just output-dev` | Show dev outputs (API URL, etc.) |
| `just build-lambda` | Build Lambda deployment package |

## Security

- API keys follow `project-{project_id}` format for multi-tenant isolation
- Lambda role has minimal DynamoDB permissions (no IAM escalation)
- TTL ensures data is automatically cleaned up
- No secrets stored in code (use environment variables)

## Roadmap

- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Cost tracking per span
- [ ] Prompt versioning
- [ ] Export to Parquet/S3
- [ ] Comparison views for A/B testing prompts

## Contributing

Contributions welcome! Please open an issue first to discuss changes.

## License

MIT

---

**Stop paying monthly fees for LLM observability. Own your data, pay only for what you use.**
