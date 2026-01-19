# LLM Tracer Dashboard

A visual interface for exploring traces and spans from your LLM applications.

---

## Why Run Locally?

When building LLM applications, you generate traces every time your code runs—during debugging, testing prompts, or iterating on agent logic.

**For MVP and small-scope development, local visualization is enough because:**

- **Fast feedback loop**: See traces instantly without network latency
- **No cloud costs**: DynamoDB Local + local tracer API = $0
- **Privacy**: Your prompts, responses, and API keys never leave your machine
- **Simple setup**: One command to start, one command to stop

Once your application matures and you need team-wide visibility or persistent storage, you can deploy the tracer API to AWS and continue using this dashboard locally—or deploy the dashboard too.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            YOUR MACHINE                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────────┐          ┌──────────────────┐                    │
│   │  Your LLM App    │          │   Reflex         │                    │
│   │                  │          │   Dashboard      │                    │
│   │  (Python code    │          │                  │                    │
│   │   using tracer   │          │  Frontend :3000  │◄──── You view here │
│   │   client)        │          │  Backend  :8002  │                    │
│   └────────┬─────────┘          └────────┬─────────┘                    │
│            │                             │                              │
│            │ Sends traces                │ Fetches traces               │
│            ▼                             ▼                              │
│   ┌─────────────────────────────────────────────────┐                   │
│   │              Tracer API (:8001)                 │                   │
│   │                                                 │                   │
│   │  Receives traces from your app                  │                   │
│   │  Serves traces to dashboard                     │                   │
│   └────────────────────┬────────────────────────────┘                   │
│                        │                                                │
│                        ▼                                                │
│   ┌─────────────────────────────────────────────────┐                   │
│   │           DynamoDB Local (:8000)                │                   │
│   │                                                 │                   │
│   │  Stores all traces and spans                    │                   │
│   └─────────────────────────────────────────────────┘                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**How it works:**

1. Your LLM application uses the `llm-tracer` client to send traces to the Tracer API
2. Tracer API stores traces in DynamoDB (local or AWS)
3. Dashboard's Python backend fetches traces from the Tracer API
4. Dashboard's frontend displays them in your browser

**Key point**: The dashboard never talks directly to your LLM app. It only reads from the Tracer API.

---

## Quick Start

### Prerequisites

- Docker installed and running
- Tracer API running at `localhost:8001` (see `service/` for setup)

### Run the Dashboard

```bash
# If you're developing/customizing the dashboard itself
just run-dev

# If you're building an LLM app and want dashboard in background
just run-dev-detached

# View logs when running in background
just logs-dev

# Stop the dashboard
just stop-dev
```

Open your browser at **http://localhost:3000**

---

## Configuration

All configuration is in the `.env` file:

```bash
# Where is your Tracer API?
TRACER_API_URL=http://localhost:8001

# Your API key (format: project-{project_id})
TRACER_API_KEY=project-dev
```

To view traces from a production tracer (AWS Lambda), simply change `TRACER_API_URL`:

```bash
TRACER_API_URL=https://your-lambda-function-url.amazonaws.com
TRACER_API_KEY=project-prod
```

Then restart the dashboard.

---

## Note: Cloud Deployment Considerations

If you want to deploy this dashboard to the cloud for team access, here's what you need to know:

### Reflex is a Full-Stack Framework

Unlike static dashboards (pure HTML/JS), Reflex applications require:

1. **A Python backend** — Reflex runs a FastAPI server that handles state management and API calls
2. **A frontend server** — Reflex serves a Next.js application
3. **WebSocket connections** — Browser maintains a live connection to the backend for reactivity

This means you **cannot** deploy Reflex as a static site to services like:
- GitHub Pages
- Netlify (static hosting)
- S3 + CloudFront (static hosting)

### Recommended Cloud Options

| Service | Why It Works | Complexity |
|---------|--------------|------------|
| **AWS ECS/Fargate** | Runs Docker containers, scales automatically | Medium |
| **AWS App Runner** | Simpler than ECS, good for single containers | Low |
| **Railway / Render** | Docker-based PaaS, easy deployment | Low |
| **EC2 / VPS** | Full control, run Docker yourself | Medium |

### What You'll Need

1. **Container registry**: Push your Docker image (ECR, Docker Hub, etc.)
2. **Persistent URL**: For the `REFLEX_API_URL` config (so frontend can find backend)
3. **Environment variables**: `TRACER_API_URL` and `TRACER_API_KEY` for your production tracer
4. **HTTPS**: Required for WebSocket connections in production

### Cost Consideration

Running a container 24/7 costs money. For small teams, consider:
- Run dashboard locally, connect to production tracer API
- Spin up dashboard only when needed (not 24/7)
- Use a small instance size (512MB RAM is usually enough)

---

## Available Commands

Run `just` to see the help menu, or `just --list` for all commands:

| Command | Description |
|---------|-------------|
| `just run-dev` | Run interactively (for dashboard development) |
| `just run-dev-detached` | Run in background (for LLM app development) |
| `just stop-dev` | Stop the dashboard |
| `just logs-dev` | View dashboard logs |
| `just ps` | Show running containers |
| `just clean-all` | Remove all containers and images |

---

## Troubleshooting

### Dashboard shows "Disconnected" or "Unhealthy"

The dashboard checks if the Tracer API is reachable. If you see this:

1. Ensure the Tracer API is running: `curl http://localhost:8001/health`
2. Check your `.env` file has the correct `TRACER_API_URL`
3. Restart the dashboard after changing `.env`

### No traces showing

1. Verify your LLM app is sending traces (check Tracer API logs)
2. Confirm `TRACER_API_KEY` in dashboard matches the project you're tracing
3. Check browser console for errors (F12 → Console)

### Port already in use

The dashboard uses ports 3000 (frontend) and 8002 (backend). If these are busy:

1. Stop other services using these ports, or
2. Modify `rxconfig.py` to use different ports

---

## Project Structure

```
dashboard/
├── Dockerfile          # Multi-stage build (dev + prod)
├── Justfile            # Task runner commands
├── .env                # Configuration (API URL, keys)
├── rxconfig.py         # Reflex framework configuration
├── pyproject.toml      # Python dependencies
└── dashboard/          # Application code
    ├── dashboard.py    # Main app, routes, pages
    ├── state.py        # Reflex state management
    ├── api.py          # Tracer API client
    └── components/     # UI components
```

---

## FAQ

**Q: Can I customize the dashboard?**
Yes. Edit files in `dashboard/dashboard/`, run `just run-dev`, and changes hot-reload automatically.

**Q: Does the dashboard store any data?**
No. The dashboard is read-only. All data lives in DynamoDB via the Tracer API.

**Q: Can multiple people use the same local dashboard?**
If they're on the same network and you bind to `0.0.0.0`, yes. But for team use, consider deploying to the cloud.

**Q: What's the difference between the basic HTML dashboard and this Reflex dashboard?**
The basic HTML dashboard (at `localhost:8001`) is embedded in the Tracer API—simple but limited. This Reflex dashboard is a full application with better visualization, filtering, and extensibility.
