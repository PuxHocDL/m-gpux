"""Full end-to-end test: auth + inference (non-stream + stream)."""
import urllib.request
import urllib.error
import json
import time

BASE = "https://puxpuxx--m-gpux-llm-api-serve.modal.run"
KEY = "sk-mgpux-8b37a191eb046c68b9805c1d381a61a2b33a7464c6c0bbe6"
MODEL = "Qwen/Qwen3.5-35B-A3B"

passed = 0
failed = 0

def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}")

# ── Wait for vLLM ──
print("=== Waiting for vLLM to be ready... ===")
start = time.time()
while True:
    try:
        r = urllib.request.urlopen(f"{BASE}/health", timeout=600)
        data = json.loads(r.read())
        elapsed = time.time() - start
        if data.get("vllm_ready"):
            print(f"  vLLM ready! ({elapsed:.1f}s)")
            break
        ready = data.get("vllm_ready")
        print(f"  [{elapsed:.0f}s] vllm_ready={ready}")
        time.sleep(10)
    except Exception as e:
        elapsed = time.time() - start
        print(f"  [{elapsed:.0f}s] Error: {e}")
        time.sleep(10)

# ── Test 1: /health ──
print("\n=== Test 1: /health (no auth) ===")
r = urllib.request.urlopen(f"{BASE}/health", timeout=30)
data = json.loads(r.read())
print(f"  Status: {r.status}")
print(f"  Body: {data}")
ok("status=200", r.status == 200)
ok("vllm_ready=True", data.get("vllm_ready") is True)

# ── Test 2: /v1/models no key => 401 ──
print("\n=== Test 2: /v1/models WITHOUT key => 401 ===")
try:
    urllib.request.urlopen(f"{BASE}/v1/models", timeout=30)
    ok("401", False)
except urllib.error.HTTPError as e:
    print(f"  Status: {e.code}")
    ok("401", e.code == 401)

# ── Test 3: /v1/models wrong key => 403 ──
print("\n=== Test 3: /v1/models WITH wrong key => 403 ===")
req = urllib.request.Request(f"{BASE}/v1/models")
req.add_header("Authorization", "Bearer sk-wrong-key")
try:
    urllib.request.urlopen(req, timeout=30)
    ok("403", False)
except urllib.error.HTTPError as e:
    print(f"  Status: {e.code}")
    ok("403", e.code == 403)

# ── Test 4: /v1/models valid key => 200 ──
print("\n=== Test 4: /v1/models WITH valid key => 200 ===")
req = urllib.request.Request(f"{BASE}/v1/models")
req.add_header("Authorization", f"Bearer {KEY}")
r = urllib.request.urlopen(req, timeout=30)
data = json.loads(r.read())
models = [m["id"] for m in data.get("data", [])]
print(f"  Status: {r.status}")
print(f"  Models: {models}")
ok("status=200", r.status == 200)
ok("model in list", MODEL in models)

# ── Test 5: Chat completion (non-streaming) ──
print("\n=== Test 5: Chat completion (non-streaming) ===")
payload = json.dumps({
    "model": MODEL,
    "messages": [{"role": "user", "content": "Say hello in 5 words."}],
    "max_tokens": 50,
    "temperature": 0.7,
    "stream": False,
}).encode()
req = urllib.request.Request(f"{BASE}/v1/chat/completions", data=payload, method="POST")
req.add_header("Authorization", f"Bearer {KEY}")
req.add_header("Content-Type", "application/json")
t0 = time.time()
r = urllib.request.urlopen(req, timeout=120)
latency = time.time() - t0
data = json.loads(r.read())
msg = data["choices"][0]["message"]["content"]
usage = data.get("usage", {})
print(f"  Status: {r.status}")
print(f"  Latency: {latency:.2f}s")
print(f"  Response: {msg}")
print(f"  Usage: {usage}")
ok("status=200", r.status == 200)
ok("has content", len(msg) > 0)

# ── Test 6: Chat completion (streaming) ──
print("\n=== Test 6: Chat completion (streaming) ===")
payload = json.dumps({
    "model": MODEL,
    "messages": [{"role": "user", "content": "Count from 1 to 5."}],
    "max_tokens": 100,
    "temperature": 0.7,
    "stream": True,
}).encode()
req = urllib.request.Request(f"{BASE}/v1/chat/completions", data=payload, method="POST")
req.add_header("Authorization", f"Bearer {KEY}")
req.add_header("Content-Type", "application/json")
t0 = time.time()
r = urllib.request.urlopen(req, timeout=120)
ttft = None
chunks = 0
full_text = ""
for line in r:
    line = line.decode().strip()
    if line.startswith("data: ") and line != "data: [DONE]":
        if ttft is None:
            ttft = time.time() - t0
        chunks += 1
        try:
            d = json.loads(line[6:])
            delta = d["choices"][0]["delta"].get("content", "")
            full_text += delta
        except Exception:
            pass
total = time.time() - t0
print(f"  Status: {r.status}")
print(f"  TTFT: {ttft:.2f}s" if ttft else "  TTFT: N/A")
print(f"  Total: {total:.2f}s")
print(f"  Chunks: {chunks}")
print(f"  Response: {full_text}")
ok("status=200", r.status == 200)
ok("has chunks", chunks > 0)
ok("has content", len(full_text) > 0)

# ── Test 7: Chat completion no key => 401 ──
print("\n=== Test 7: Chat /v1/chat/completions WITHOUT key => 401 ===")
payload = json.dumps({
    "model": MODEL,
    "messages": [{"role": "user", "content": "Hi"}],
    "stream": False,
}).encode()
req = urllib.request.Request(f"{BASE}/v1/chat/completions", data=payload, method="POST")
req.add_header("Content-Type", "application/json")
try:
    urllib.request.urlopen(req, timeout=30)
    ok("401", False)
except urllib.error.HTTPError as e:
    print(f"  Status: {e.code}")
    ok("401", e.code == 401)

# ── Summary ──
print(f"\n{'='*40}")
print(f"  PASSED: {passed}/{passed+failed}")
print(f"  FAILED: {failed}/{passed+failed}")
print(f"{'='*40}")
