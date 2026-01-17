"""A custom LLM tracing service"""

import os
import logging
from datetime import datetime, UTC
from typing import List, Optional, Dict, Any
from uuid import uuid4

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, HTTPException, Query, Header, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .models import (
    Trace, Span, TraceCreate, SpanCreate, TraceQuery,
    TraceListResponse, SpanCompleteRequest, TraceCompleteRequest
)
from .storage_dynamodb import DynamoDBStorage
from .auth import get_api_key, extract_project_id
from .rate_limit import RateLimiter

load_dotenv(find_dotenv(usecwd=True), override=False)

# configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title = "LLM Tracer",
    description = "A self hosted LLM tracing and observability solution with multi-project support",
    version = "1.0.0",
)


CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:*,http://127.0.0.1:*")  # Dev default

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

# Rate limit: configurable via RATE_LIMIT_RPM env var (default: 60)
# Local/dev uses default, prod controlled via Terraform
rate_limit_rpm = int(os.getenv("RATE_LIMIT_RPM", "60"))
rate_limiter = RateLimiter(requests_per_minute=rate_limit_rpm)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    await rate_limiter.check_rate_limit(request)
    response = await call_next(request)
    return response

# initialize storage
storage = DynamoDBStorage()

#=====================
# TRACE Endpoints
#=====================

@app.post("/api/traces", response_model=Dict[str, str])
async def create_trace(
    trace: TraceCreate,
    x_api_key: str = Depends(get_api_key)
):
    """Create a new trace. Requires API key for authentication.
    A trace represents a complete execution flow (e.g. One agent run)
    """
    try:
        # valudate API key and get project_id
        api_project_id = extract_project_id(x_api_key)

        # Security check: verify project_id in request matches API key
        if trace.project_id != api_project_id:
            raise HTTPException(
                status_code=403,
                detail=f"Project ID mismatch: API key is for '{api_project_id}' but request is for '{trace.project_id}'"
            )
        
        trace_id = str(uuid4())
        trace_obj = Trace(
            trace_id=trace_id,
            name=trace.name,
            project_id=api_project_id,
            start_time=datetime.now(UTC),
            tags=trace.tags or [],
            metadata=trace.metadata,
            user_id=trace.user_id,
            session_id=trace.session_id,
        )

        await storage.save_trace(trace_obj)
        logger.info(f"Created trace: {trace_id} - {trace.name} [project: {trace.project_id}] ")

        return {"trace_id": trace_id, "status": "created"}
    
    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error creating trace: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 


@app.post("/api/traces/{trace_id}/spans", response_model=Dict[str, str])
async def create_span(
    trace_id: str,
    span: SpanCreate,
    x_api_key: str = Depends(get_api_key)
):
    """Add a span to a trace. Requires API key for authentication.
    Spans represent individual operations (LLM calls, tool calls, etc.)
    """
    try:

        # validate API key and get project_id
        api_project_id = extract_project_id(x_api_key)

        # Security check: verify trace belongs to project
        trace = await storage.get_trace(trace_id, project_id=api_project_id)
        if not trace:
            raise HTTPException(
                status_code=404, 
                detail=f"Trace {trace_id} not found for project {api_project_id}"
            )

        span_id = str(uuid4())
        span_data = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=span.parent_span_id,
            name=span.name,
            span_type=span.span_type,
            start_time=datetime.now(UTC),
            end_time=None,
            duration_ms=None,
            input_data=span.input_data or {},
            output_data=span.output_data or {},
            metadata=span.metadata or {},
            model=span.model,
            tokens_input=span.tokens_input,
            tokens_output=span.tokens_output,
            cost_usd=span.cost_usd,
            error=span.error,
        )

        await storage.save_span(span_data)
        logger.info(f"Created span: {span_id} - {span.name} in trace {trace_id}")

        return {"span_id": span_id, "status": "created"}
    
    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error creating span: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Patch for partial field updates incrementally as the Agent progresses for a specific trace_id
@app.patch("/api/spans/{span_id}/complete")
async def complete_span(
    span_id: str,
    request: SpanCompleteRequest,
    x_api_key: str = Depends(get_api_key)
):
    """Mark a span complete with final data. Requires API key for authentication."""
    try:
        # Validate API key, here we trust the span exists if API key is valid
        api_project_id = extract_project_id(x_api_key)

        # Get span and verify it belongs to a trace owned by this project
        span = await storage.get_span(span_id)
        if not span:
            raise HTTPException(status_code=404, detail=f"Span {span_id} not found")

        # Verify trace ownership
        trace = await storage.get_trace(span['trace_id'], project_id=api_project_id)
        if not trace:
            raise HTTPException(
                status_code=403,
                detail=f"Span {span_id} belongs to a trace not owned by this project {api_project_id}"
            )
        
        end_time = datetime.now(UTC)
        await storage.complete_span(
            span_id=span_id,
            end_time=end_time,
            output_data=request.output_data,
            error=request.error,
            tokens_input=request.tokens_input,
            tokens_output=request.tokens_output,
            cost_usd=request.cost_usd,
        )

        logger.info(f"Completed span: {span_id}")
        return {"span_id": span_id, "status": "completed"}
    
    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error completing span: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/traces/{trace_id}/complete")
async def complete_trace(
    trace_id: str,
    request: TraceCompleteRequest,
    x_api_key: str = Depends(get_api_key)
):
    """Mark a trace complete with final data. Requires API key for authentication."""
    try:
        # Validate API key and trace to be completed belongs to the project
        api_project_id = extract_project_id(x_api_key)
        
        trace = await storage.get_trace(trace_id, project_id=api_project_id)
        if not trace:
            raise HTTPException(
                status_code=404,
                detail=f"Trace {trace_id} not found for project {api_project_id}"
            )

        end_time = datetime.now(UTC)
        await storage.complete_trace(
            trace_id=trace_id,
            end_time=end_time,
            output=request.output,
        )

        logger.info(f"Completed trace: {trace_id}")
        return {"trace_id": trace_id, "status": "completed"}
    
    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error completing trace: {e}")
        raise HTTPException(status_code=500, detail=str(e))

#=====================
# Query Endpoints
#=====================

@app.get("/api/traces", response_model=TraceListResponse)
async def get_traces(
    limit: int = Query(50, ge=1, le=1000),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tags: Optional[str] = None,  # for convenience instead of list of tags, comma separated string
    x_api_key: str = Depends(get_api_key)
):
    """Query traces within optional filters; only returns traces for the project associated with the API key"""
    try:
        # Get project_id from API key
        api_project_id = extract_project_id(x_api_key)

        tag_list = tags.split(",") if tags else None  # this is how Trace model stores tags

        # Object for filterimng traces from DB
        query = TraceQuery(
            project_id=api_project_id,
            limit=limit,
            cursor=cursor,
            user_id=user_id,
            session_id=session_id,
            tags=tag_list,
        )
        result = await storage.get_traces(query)

        # span_count and total_cost are now denormalized on the trace record
        return TraceListResponse(
            traces=result.get("items", []),
            next_cursor=result.get("next_cursor", None),
            has_more=result.get("next_cursor") is not None,
            count=len(result.get("items", []))
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error querying traces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/traces/{trace_id}", response_model=Dict[str, Any])
async def get_trace(
    trace_id: str,
    x_api_key: str = Depends(get_api_key)
):
    """Get a complete trace with all its spans. requires API key for authentication"""
    try:
        # Get project_id from API key
        api_project_id = extract_project_id(x_api_key)

        trace = await storage.get_trace(trace_id, project_id=api_project_id)
        if not trace:
            raise HTTPException(
                status_code=404,
                detail=f"Trace {trace_id} not found for project {api_project_id}"
            )
        
        spans = await storage.get_spans(trace_id, project_id=api_project_id)
        return {
            "trace": trace,
            "spans": spans,
            "span_count": len(spans),
        }
    
    except HTTPException:
        raise  # to cover for specifically httpexception raised above,
    
    except Exception as e:
        logger.error(f"Error getting trace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats(    
    x_api_key: str = Depends(get_api_key)
):
    """Get overall statistics; requires API key for authentication"""
    try:
        # Get project_id from API key
        api_project_id = extract_project_id(x_api_key)

        stats = await storage.get_stats(project_id=api_project_id)
        return stats
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


#==============
# DASHBOARD
#==============

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Simple Dashboard UI"""
    html = """
      <!DOCTYPE html>
        <html>
        <head>
            <title>LLM Tracer Dashboard</title>
            <style>
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    max-width: 1200px; 
                    margin: 0 auto; 
                    padding: 20px;
                    background: #f5f5f5;
                }
                h1 { color: #333; }
                .auth-section {
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }
                .stats { 
                    display: grid; 
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px; 
                    margin: 20px 0;
                }
                .stat-card {
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .stat-value { font-size: 2em; font-weight: bold; color: #0066cc; }
                .stat-label { color: #666; margin-top: 5px; }
                .traces { margin-top: 30px; }
                .trace-card {
                    background: white;
                    padding: 15px;
                    margin: 10px 0;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .trace-name { font-weight: bold; font-size: 1.1em; }
                .trace-meta { color: #666; font-size: 0.9em; margin-top: 5px; }
                .loading { text-align: center; padding: 20px; color: #666; }
                input { padding: 10px; width: 300px; margin-right: 10px; }
                button { padding: 10px 20px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #0052a3; }
            </style>
        </head>
        <body>
            <h1>🔍 LLM Tracer Dashboard</h1>
            
            <div class="auth-section">
                <h3>API Key</h3>
                <input type="password" id="apiKey" placeholder="Enter your API key (e.g., project-myproject)" />
                <button onclick="loadData()">Load Data</button>
                <p style="font-size: 0.9em; color: #666;">API key format: project-{your-project-id}</p>
            </div>
            
            <div class="stats" id="stats">
                <div class="loading">Enter API key to load statistics...</div>
            </div>
            
            <div class="traces">
                <h2>Recent Traces</h2>
                <div id="traces">
                    <div class="loading">Enter API key to load traces...</div>
                </div>
            </div>
            
            <script>
                let apiKey = '';
                
                async function loadData() {
                    apiKey = document.getElementById('apiKey').value;
                    if (!apiKey) {
                        alert('Please enter an API key');
                        return;
                    }
                    await loadStats();
                    await loadTraces();
                }
                
                async function loadStats() {
                    try {
                        const response = await fetch('/api/stats', {
                            headers: { 'X-API-Key': apiKey }
                        });
                        
                        if (!response.ok) {
                            throw new Error('Authentication failed');
                        }
                        
                        const stats = await response.json();
                        
                        document.getElementById('stats').innerHTML = `
                            <div class="stat-card">
                                <div class="stat-value">${stats.total_traces}</div>
                                <div class="stat-label">Total Traces</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">${stats.total_spans}</div>
                                <div class="stat-label">Total Spans</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">${stats.total_tokens?.toLocaleString() || 'N/A'}</div>
                                <div class="stat-label">Total Tokens</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">$${stats.total_cost?.toFixed(2) || '0.00'}</div>
                                <div class="stat-label">Total Cost</div>
                            </div>
                        `;
                    } catch (error) {
                        document.getElementById('stats').innerHTML = '<div class="loading" style="color: red;">Error: ' + error.message + 
  '</div>';
                    }
                }
                
                async function loadTraces() {
                    try {
                        const response = await fetch('/api/traces?limit=20', {
                            headers: { 'X-API-Key': apiKey }
                        });

                        if (!response.ok) {
                            throw new Error('Authentication failed');
                        }

                        const data = await response.json();
                        const traces = data.traces;

                        if (traces.length === 0) {
                            document.getElementById('traces').innerHTML = '<p>No traces yet</p>';
                            return;
                        }

                        document.getElementById('traces').innerHTML = traces.map(trace => `
                            <div class="trace-card">
                                <div class="trace-name">${trace.name}</div>
                                <div class="trace-meta">
                                    ID: ${trace.trace_id}<br>
                                    Project: ${trace.project_id}<br>
                                    Started: ${new Date(trace.start_time).toLocaleString()}<br>
                                    Duration: ${trace.duration_ms ? (trace.duration_ms/1000).toFixed(2) + 's' : 'In progress...'}
                                </div>
                            </div>
                        `).join('');
                    } catch (error) {
                        document.getElementById('traces').innerHTML = '<div class="loading" style="color: red;">Error: ' + error.message +
  '</div>';
                    }
                }
            </script>
        </body>
        </html>
      """

    return html


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "LLM Tracer",
        "version": "1.0.0",
        "features": ["Multi-project-support", "Cost tracking", "Detailed trace analysis"],
        "storage": storage.get_type(),
        "timestamp": datetime.now(UTC).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
