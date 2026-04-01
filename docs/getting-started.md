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
