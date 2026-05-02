"""
FastAPI example for m-gpux host asgi.

Deploy:
    cd examples/host-asgi
    m-gpux host asgi --entry main:app
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone
import platform
import os

app = FastAPI(
    title="M-GPUX ASGI Demo",
    description="A sample FastAPI app deployed via m-gpux host asgi",
    version="1.0.0",
)


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>M-GPUX ASGI Demo</title>
        <style>
            body { font-family: system-ui; background: #1e1e2e; color: #cdd6f4; 
                   display: flex; justify-content: center; padding: 3rem; }
            .box { background: #313244; border-radius: 12px; padding: 2rem; max-width: 600px; width: 100%; }
            h1 { color: #cba6f7; }
            a { color: #89b4fa; }
            code { background: #45475a; padding: 0.2em 0.4em; border-radius: 4px; font-size: 0.9em; }
            .endpoint { margin: 0.5rem 0; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>🚀 M-GPUX ASGI Demo</h1>
            <p>This FastAPI app is running on Modal via <code>m-gpux host asgi</code>.</p>
            <h3>Try these endpoints:</h3>
            <div class="endpoint">📋 <a href="/docs">/docs</a> — Swagger UI</div>
            <div class="endpoint">🏥 <a href="/health">/health</a> — Health check</div>
            <div class="endpoint">📊 <a href="/info">/info</a> — System info</div>
            <div class="endpoint">👋 <a href="/hello/world">/hello/{name}</a> — Greeting</div>
            <div class="endpoint">🧮 <a href="/fibonacci/10">/fibonacci/{n}</a> — Compute Fibonacci</div>
        </div>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/info")
async def info():
    return {
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "hostname": platform.node(),
    }


@app.get("/hello/{name}")
async def hello(name: str):
    return {"message": f"Hello, {name}! 👋", "from": "m-gpux host asgi"}


@app.get("/fibonacci/{n}")
async def fibonacci(n: int):
    """Compute the n-th Fibonacci number (capped at 90 to prevent abuse)."""
    if n < 0 or n > 90:
        return {"error": "n must be between 0 and 90"}
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return {"n": n, "result": a}


@app.post("/echo")
async def echo(request: Request):
    """Echo back the JSON body you send."""
    body = await request.json()
    return {"echo": body}
