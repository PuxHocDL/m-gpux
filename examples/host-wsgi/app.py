"""
Flask example for m-gpux host wsgi.

Deploy:
    cd examples/host-wsgi
    m-gpux host wsgi --entry app:app
"""

from flask import Flask, jsonify, request, render_template_string
from datetime import datetime, timezone
import platform
import os

app = Flask(__name__)

# In-memory task list for demo purposes
tasks: list[dict] = [
    {"id": 1, "title": "Deploy this app with m-gpux", "done": True},
    {"id": 2, "title": "Try the REST API", "done": False},
    {"id": 3, "title": "Check /health endpoint", "done": False},
]

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>M-GPUX WSGI Demo</title>
    <style>
        body { font-family: system-ui; background: #1e1e2e; color: #cdd6f4;
               display: flex; justify-content: center; padding: 3rem; }
        .box { background: #313244; border-radius: 12px; padding: 2rem; max-width: 600px; width: 100%; }
        h1 { color: #a6e3a1; }
        a { color: #89b4fa; }
        code { background: #45475a; padding: 0.2em 0.4em; border-radius: 4px; font-size: 0.9em; }
        ul { list-style: none; padding: 0; }
        li { padding: 0.4rem 0; border-bottom: 1px solid #45475a; }
        .done { text-decoration: line-through; color: #6c7086; }
    </style>
</head>
<body>
    <div class="box">
        <h1>📝 M-GPUX WSGI Demo — Task Board</h1>
        <p>Flask app deployed via <code>m-gpux host wsgi</code>.</p>
        <h3>Tasks</h3>
        <ul>
        {% for t in tasks %}
            <li class="{{ 'done' if t.done else '' }}">
                {{ '✅' if t.done else '⬜' }} {{ t.title }}
            </li>
        {% endfor %}
        </ul>
        <h3>REST API</h3>
        <p><code>GET /api/tasks</code> — list tasks</p>
        <p><code>POST /api/tasks</code> — add task <code>{"title": "..."}</code></p>
        <p><code>PATCH /api/tasks/&lt;id&gt;</code> — toggle done</p>
        <p><code>DELETE /api/tasks/&lt;id&gt;</code> — remove task</p>
        <p><code>GET /health</code> — health check</p>
    </div>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(TEMPLATE, tasks=tasks)


@app.route("/health")
def health():
    return jsonify(status="healthy", timestamp=datetime.now(timezone.utc).isoformat())


@app.route("/info")
def info():
    return jsonify(
        python=platform.python_version(),
        system=platform.system(),
        machine=platform.machine(),
        cpu_count=os.cpu_count(),
    )


@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    return jsonify(tasks=tasks)


@app.route("/api/tasks", methods=["POST"])
def add_task():
    data = request.get_json(force=True)
    title = data.get("title", "").strip()
    if not title:
        return jsonify(error="title is required"), 400
    new_id = max((t["id"] for t in tasks), default=0) + 1
    task = {"id": new_id, "title": title, "done": False}
    tasks.append(task)
    return jsonify(task=task), 201


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
def toggle_task(task_id: int):
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = not t["done"]
            return jsonify(task=t)
    return jsonify(error="not found"), 404


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id: int):
    for i, t in enumerate(tasks):
        if t["id"] == task_id:
            tasks.pop(i)
            return jsonify(ok=True)
    return jsonify(error="not found"), 404
