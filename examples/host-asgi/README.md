# FastAPI (ASGI) Example

A sample FastAPI app to test `m-gpux host asgi`.

## Deploy

```bash
cd examples/host-asgi
m-gpux host asgi --entry main:app
```

The wizard will ask about compute, pip packages (auto-detects `requirements.txt`), and deployment mode.

## Endpoints

| Path | Description |
|------|-------------|
| `/` | Landing page |
| `/docs` | Swagger UI (auto-generated) |
| `/health` | Health check JSON |
| `/info` | System info |
| `/hello/{name}` | Greeting |
| `/fibonacci/{n}` | Compute Fibonacci |
| `POST /echo` | Echo JSON body |

## Stop

```bash
m-gpux stop
```
