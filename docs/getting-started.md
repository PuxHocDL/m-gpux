# Getting Started

This guide helps you install and run `m-gpux` in minutes.

## Prerequisites

- Python 3.10+
- Modal account credentials (`token_id` and `token_secret`)
- `modal` CLI installed and available in your shell

## Install

```bash
git clone https://github.com/PuxHocDL/m-gpux.git
cd m-gpux
pip install -e .
```

## Quick Start

### Add your first profile

```bash
m-gpux account add
```

You will be prompted for:

- Profile name
- Modal Token ID
- Modal Token Secret

### List profiles

```bash
m-gpux account list
```

### Launch compute hub

```bash
m-gpux hub
```

### Check costs

```bash
m-gpux billing usage --days 30 --all
```

## Typical first-day workflow

1. Add a personal profile.
2. Add a work or team profile.
3. Switch between profiles with `account switch`.
4. Start GPU sessions through `hub`.
5. Review usage weekly with `billing usage`.

## Deploy an LLM API

Turn any HuggingFace model into an OpenAI-compatible API with authentication:

### 1. Create an API key

```bash
m-gpux serve keys create --name my-key
```

### 2. Deploy with the interactive wizard

```bash
m-gpux serve deploy
```

The wizard guides you through model, GPU, context length, keep-warm, and API key selection.

### 3. Test your endpoint

```bash
curl https://<your-workspace>--m-gpux-llm-api-serve.modal.run/v1/models \
  -H "Authorization: Bearer sk-mgpux-..."
```

### 4. Use with OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://<your-workspace>--m-gpux-llm-api-serve.modal.run/v1",
    api_key="sk-mgpux-...",
)

response = client.chat.completions.create(
    model="your-model-name",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

### 5. Stop when done

```bash
m-gpux serve stop
# or stop all running apps
m-gpux stop --all
```
