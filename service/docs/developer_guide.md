# Developer Guide

This guide explains the service module structure and how to use it for local development, testing, and deployment.

## Local Development Environment

### Docker and docker-compose

The `Dockerfile` and `docker-compose.yml` create a local environment that mimics the AWS cloud architecture:

- **DynamoDB Local**: Runs Amazon's DynamoDB Local container on port 8000, providing the same API as AWS DynamoDB
- **Service Container**: Runs the FastAPI application on port 8001, configured to use the local DynamoDB

This setup serves two purposes:

1. **Active Development**: Test features and debug locally before deploying to AWS
2. **CI/CD Testing**: Run integration tests in GitHub Actions without requiring AWS credentials or incurring costs

The docker-compose configuration uses environment variables with sensible defaults (`llm-tracer-dev-traces`, `llm-tracer-dev-spans`) so you can spin up the environment without configuration.

```bash
# Start the local environment
just up

# View logs
just logs

# Stop everything
just down
```

## scripts/

### build_lambda_package.sh

Creates the Lambda deployment package (`dist/lambda.zip`). This script:

1. Exports dependencies from `uv.lock` (excluding dev dependencies)
2. Installs packages for the Lambda runtime (linux x86_64, Python 3.12)
3. Copies application source code and the Lambda handler
4. Creates a zip file and verifies it's under the 50MB Lambda limit

Run with: `./scripts/build_lambda_package.sh` or `just dev-build-lambda`

### create_dynamodb_tables.py

Creates DynamoDB tables for both local testing and AWS deployment. It reads schema definitions from `dynamodb_schemas.py` and:

- Creates `traces` and `spans` tables with appropriate indexes
- Enables TTL for automatic data expiration (90 days, AWS only)
- Works with local DynamoDB (`--endpoint http://localhost:8000`) or AWS

### dynamodb_schemas.py

Defines table schemas in a reusable format:

- **TRACES_SCHEMA**: Primary key `trace_id`, GSI on `project_id + start_time` for querying by project
- **SPANS_SCHEMA**: Primary key `span_id`, GSI on `trace_id` for fetching all spans in a trace

Keeping schemas separate allows flexibility in table creation and makes it easy to modify indexes without changing application code.

## src/

### server.py

The FastAPI application entry point. Defines all HTTP endpoints:

- `POST /api/traces` - Create a new trace
- `POST /api/traces/{trace_id}/spans` - Add a span to a trace
- `PATCH /api/spans/{span_id}/complete` - Mark a span as completed with output/metrics
- `PATCH /api/traces/{trace_id}/complete` - Mark a trace as completed
- `GET /api/traces` - List traces with pagination and filters
- `GET /api/traces/{trace_id}` - Get a trace with all its spans
- `GET /api/stats` - Get project statistics (trace count, tokens, cost)
- `GET /health` - Health check endpoint
- `GET /` - Simple dashboard UI

Also configures CORS, rate limiting middleware, and initializes the storage backend.

### models.py

Pydantic models for request/response validation and DynamoDB serialization:

- **TraceCreate/Trace**: Trace data models with validation
- **SpanCreate/Span**: Span data models supporting various types (llm, tool, agent, function, etc.)
- **TraceQuery/TraceListResponse**: Query parameters and paginated response
- **SpanCompleteRequest/TraceCompleteRequest**: Partial update models

Includes automatic truncation of large fields to stay within DynamoDB's 400KB item limit.

### storage_dynamodb.py

DynamoDB storage backend implementing all data operations:

- Save/get/complete traces and spans
- Query traces by project with pagination (cursor-based)
- Calculate project statistics
- Automatic TTL (90-day retention)

Handles DynamoDB-specific concerns like Decimal conversion for costs and datetime validation.

### auth.py

API key authentication middleware. Keys follow the format `project-{project_id}`:

- Validates API keys against the `API_KEYS` environment variable
- Extracts project ID from the key for multi-tenant isolation
- Can be disabled via `API_KEY_REQUIRED=false` for development

### rate_limit.py

In-memory rate limiter using a sliding window algorithm. Limits requests per IP address (default: 60 requests/minute). Configurable via `RATE_LIMIT_RPM` environment variable.

## Justfile

[Just](https://github.com/casey/just) is a command runner (like make, but simpler). The `Justfile` contains shortcuts for common development tasks.

### Justfile vs Justfile.example

- **Justfile**: Your personal workflow automation. Add commands you use frequently. This file is git-tracked but intended to be customized.
- **Justfile.example**: Reference of all available commands organized by category. Copy commands you need into your `Justfile`.

The example file includes commands for:

- **docker-***: Container management (up, down, logs, shell access)
- **local-***: Local DynamoDB operations (create tables, scan data, reset)
- **aws-***: AWS DynamoDB operations (requires configured credentials)
- **api-***: API testing shortcuts (health check, list traces, create test data)
- **dev-***: Development tasks (run tests, lint, format, local server)
- **lambda-***: Lambda packaging and deployment

Use what you need. The Justfile is a developer convenience tool, not a required part of the build process.
