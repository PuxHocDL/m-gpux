"""Regenerate modal_runner.py for deployment."""
from m_gpux.commands.serve import SERVE_TEMPLATE, _get_active_keys
from m_gpux.commands._metrics_snippet import FUNCTIONS

model = "Qwen/Qwen3.5-35B-A3B"
gpu = "A100-80GB"
keys = _get_active_keys()
api_key = keys[0] if keys else "sk-mgpux-test"

env_dict = '{"HF_HUB_ENABLE_HF_TRANSFER": "1"}'
volumes_dict = '{\n        "/root/.cache/huggingface": hf_cache,\n        "/root/.cache/vllm": vllm_cache,\n    }'

script = (SERVE_TEMPLATE
    .replace("{model_name}", model)
    .replace("{gpu_type}", gpu)
    .replace("{api_key}", api_key)
    .replace("{max_model_len}", "4096")
    .replace("{keep_warm}", "1")
    .replace("ENV_DICT_PLACEHOLDER", env_dict)
    .replace("VOLUMES_PLACEHOLDER", volumes_dict)
    .replace("# __METRICS__", FUNCTIONS))

with open("modal_runner.py", "w", encoding="utf-8") as f:
    f.write(script)

for i, line in enumerate(script.split("\n")):
    if "Popen" in line or "API_KEY" in line or "port 800" in line:
        print(f"  L{i}: {line.strip()}")
print("Generated OK")
