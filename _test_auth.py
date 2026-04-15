"""Test auth proxy on deployed endpoint."""
import urllib.request
import urllib.error
import json

BASE = "https://puxpuxx--m-gpux-llm-api-serve.modal.run"
GOOD_KEY = "sk-mgpux-8b37a191eb046c68b9805c1d381a61a2b33a7464c6c0bbe6"

# Test 1: /health (no auth)
print("=== Test 1: /health (no auth) ===")
try:
    r = urllib.request.urlopen(f"{BASE}/health", timeout=600)
    print(f"  Status: {r.status}")
    print(f"  Body: {json.loads(r.read())}")
except Exception as e:
    print(f"  Error: {e}")

# Test 2: /v1/models WITHOUT key (should be 401)
print("\n=== Test 2: /v1/models without key ===")
try:
    r = urllib.request.urlopen(f"{BASE}/v1/models", timeout=30)
    print(f"  Status: {r.status} (FAIL - should be 401)")
except urllib.error.HTTPError as e:
    print(f"  Status: {e.code} (expected 401)")

# Test 3: /v1/models WITH correct key
print("\n=== Test 3: /v1/models with valid key ===")
req = urllib.request.Request(f"{BASE}/v1/models")
req.add_header("Authorization", f"Bearer {GOOD_KEY}")
try:
    r = urllib.request.urlopen(req, timeout=60)
    data = json.loads(r.read())
    models = [m["id"] for m in data.get("data", [])]
    print(f"  Status: {r.status}")
    print(f"  Models: {models}")
except urllib.error.HTTPError as e:
    print(f"  Status: {e.code}")
    print(f"  Body: {e.read().decode()}")

# Test 4: /v1/models WITH wrong key (should be 403)
print("\n=== Test 4: /v1/models with wrong key ===")
req = urllib.request.Request(f"{BASE}/v1/models")
req.add_header("Authorization", "Bearer sk-mgpux-wrongkey123")
try:
    r = urllib.request.urlopen(req, timeout=30)
    print(f"  Status: {r.status} (FAIL - should be 403)")
except urllib.error.HTTPError as e:
    print(f"  Status: {e.code} (expected 403)")
