---
name: m-gpux
description: Provision and manage Modal GPU workloads — run scripts, launch Jupyter, open shells, check billing, and auto-rotate across accounts for cost optimization.
user-invocable: true
metadata: { "openclaw": { "requires": { "bins": ["m-gpux", "modal"] }, "emoji": "🚀" } }
---

# m-gpux — Modal GPU Orchestrator Skill

You can use the `m-gpux` CLI to manage serverless GPU compute on Modal. This skill lets you help the user provision GPUs, run Python scripts, check billing, and intelligently rotate across multiple Modal accounts to maximize free credits ($30/account/month).

## Available Commands

### Account Management
```bash
# List all profiles with billing (used / remaining credits)
m-gpux account list

# Add a new profile — paste the full modal token command or fill manually
m-gpux account add

# Switch active profile
m-gpux account switch <profile-name>
```

### GPU Hub (Interactive Provisioning)
```bash
# Launch interactive GPU provisioning wizard
# Step 0: Select workspace (0=AUTO smart pick)
# Step 1: Choose GPU (T4/L4/A10G/A100/A100-80GB/H100)
# Step 2: Choose app (Jupyter / Python Script / Bash Shell)
# Step 3: Environment setup (requirements.txt auto-detect)
# Step 4: File upload config (exclude patterns like .venv, __pycache__)
m-gpux hub
```

### Billing
```bash
# Check usage for all accounts
m-gpux billing usage --all

# Check usage for specific account
m-gpux billing usage --account <profile-name>

# Open Modal dashboard
m-gpux billing open
```

## Smart Cost Optimization

When the user asks to run something on a GPU, use these strategies:

1. **Auto-rotate accounts**: Run `m-gpux account list` to see all balances first. Pick the account with the most remaining credit.
2. **Budget awareness**: Each account gets $30/month, resets on the 1st. If a user has 16 accounts, that's $480/month total.
3. **GPU cost awareness** (approximate per-hour):
   - T4: ~$0.59/hr (cheapest, good for light inference)
   - L4: ~$0.80/hr
   - A10G: ~$1.10/hr
   - A100 40GB: ~$3.10/hr
   - A100 80GB: ~$4.06/hr
   - H100: ~$4.89/hr (most expensive)

When recommending GPUs, consider the task:
- **Light inference / testing**: T4 or L4
- **Training small models / fine-tuning**: A10G or A100
- **Large model inference (7B+ params)**: A100-80GB or H100
- **Training large models**: H100 or A100-80GB

## Example Workflows

### User: "Run my training script on a GPU"
1. Check balances: `m-gpux account list`
2. Recommend the best account (most credit) and appropriate GPU
3. Guide through: `m-gpux hub` → select auto → pick GPU → run script

### User: "How much credit do I have left?"
Run: `m-gpux account list` and summarize the table.

### User: "Launch a Jupyter notebook with an A100"
Guide: `m-gpux hub` → auto account → A100 → Jupyter

### User: "Add my new Modal account"
They can paste: `modal token set --token-id ak-xxx --token-secret as-xxx --profile=name`
Run: `m-gpux account add` and paste the command.
