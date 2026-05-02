# Flask (WSGI) Example

A sample Flask task-board app to test `m-gpux host wsgi`.

## Deploy

```bash
cd examples/host-wsgi
m-gpux host wsgi --entry app:app
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Task board UI |
| GET | `/health` | Health check |
| GET | `/info` | System info |
| GET | `/api/tasks` | List all tasks |
| POST | `/api/tasks` | Add task (`{"title": "..."}`) |
| PATCH | `/api/tasks/<id>` | Toggle done |
| DELETE | `/api/tasks/<id>` | Remove task |

## Test with curl

```bash
# Add a task
curl -X POST <URL>/api/tasks -H 'Content-Type: application/json' -d '{"title":"Buy milk"}'

# List tasks
curl <URL>/api/tasks

# Toggle task #1
curl -X PATCH <URL>/api/tasks/1
```

## Stop

```bash
m-gpux stop
```
