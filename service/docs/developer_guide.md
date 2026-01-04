# Developer Guide

This guide explains the service module structure and how to use it for local development, testing, and deployment.

## Local Development Environment

### Prerequisites

- Python 3.12
- Docker
- Docker Compose
- **All the commands below must be run from service/ directory and not root one, locally.**
- aws cli
- Just for Justfile automations

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

### Network Architecture and Ports

Understanding the network architecture is important for debugging and writing tests. There are two contexts where services communicate differently:

| Service | Docker Internal | Host Machine |
|---------|-----------------|--------------|
| DynamoDB Local | `dynamodb:8000` | `localhost:8000` |
| FastAPI Service | `service:8001` | `localhost:8001` |

**Why this matters for contributors:**

1. **Inside Docker containers** (e.g., the FastAPI service container): Use Docker's internal DNS names. The service connects to DynamoDB via `http://dynamodb:8000` because both containers are on the same Docker network.

2. **From your host machine** (e.g., running tests, curl commands, browser): Use `localhost` with the exposed ports. Tests connect to DynamoDB via `http://localhost:8000`.

3. **FastAPI TestClient**: A common point of confusion. TestClient talks directly to the FastAPI app (no HTTP network involved), but the app's storage layer still connects to DynamoDB. So even when using TestClient, you need DynamoDB Local running:

   ```
   TestClient -> FastAPI app (in-process) -> DynamoDBStorage -> DynamoDB Local (localhost:8000)
   ```

This is why integration tests set `DYNAMODB_ENDPOINT_URL=http://localhost:8000` - the test process runs on the host, so it uses localhost to reach DynamoDB Local.

## Running Tests

### Unit Tests

Unit tests use [moto](https://github.com/getmoto/moto) to mock AWS services. No external dependencies required:

```bash
uv run pytest tests/unit/ -v
```

### Integration Tests

Integration tests require DynamoDB Local running. They test the full request flow through the FastAPI app:

```bash
# Start DynamoDB Local (if not already running)
just up

# Run integration tests
uv run pytest tests/integration/ -v
```

**Test Configuration:**

Integration tests configure the environment before importing the app:

```python
import os

# Must be set BEFORE importing the app
os.environ["DYNAMODB_ENDPOINT_URL"] = "http://localhost:8000"
os.environ["DYNAMODB_TRACES_TABLE"] = "llm-tracer-dev-traces"  # these names must match with create_dynamodb_tables.py script
os.environ["DYNAMODB_SPANS_TABLE"] = "llm-tracer-dev-spans"  # these names must match with create_dynamodb_tables.py script
os.environ["API_KEY_REQUIRED"] = "true"
os.environ["API_KEYS"] = "project-test"

from service.src.server import app  # Now import the app
```

The order matters because the FastAPI app initializes `DynamoDBStorage` at import time, reading environment variables then.

### Running All Tests

```bash
# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=service/src --cov-report=term-missing
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

**NOTE:**
*In this script you will find a lot of caveat functions like convert_decimal_to_float, convert_datetime_to_str, etc. These are used to convert the data types from DynamoDB to Python and vice versa. Because DynamoDB only supports a limited set of data types from Python, we need to convert the data types to and from Python types for unsupported ones like Decimal and datetime.*

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
