<div align="center">

# Kiro Gateway for Claude Code

**Use your Kiro (Amazon Q Developer) subscription inside Claude Code — no Anthropic bill.**

Fork of [@Jwadow/kiro-gateway](https://github.com/Jwadow/kiro-gateway) (AGPL-3.0), preconfigured and documented for **Claude Code** users.
Cloning this repo and telling your AI agent *"set up Claude Code"* should be enough — see [AGENTS.md](AGENTS.md#section-0--automatic-claude-code-setup-read-this-first).

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

</div>

---

## How it works

```
Claude Code  ──(Anthropic API)──▶  localhost:8000  ──(Kiro API)──▶  Amazon Q Developer
             ANTHROPIC_BASE_URL         this gateway                your Kiro quota
```

The gateway translates Claude Code's `/v1/messages` requests (streaming, tool use,
`count_tokens` for auto-compaction) into Kiro API calls and streams the answers back.
Your prompts never go to Anthropic — they go to Kiro under your existing subscription.

### What's already handled for Claude Code in this fork

| Claude Code behavior | Gateway handling |
|---|---|
| In-message `role: "system"` reminders (`<system-reminder>`, `<local-command-caveat>`) | Accepted and folded to `user` in order (no `422`) |
| `POST /v1/messages/count_tokens` for auto-compaction | Estimated locally with Claude correction |
| Deferred tool references (Claude Code v2.1.69+) | Forward-compatible parsing |
| 30+ tools → Kiro `Improperly formed request` | `AUTO_TRIM_PAYLOAD=true` preset + tool docs moved to system prompt |
| Kiro `429` rate limits | Exponential-backoff retry before streaming starts |
| Long agentic sessions | Streaming with first-token retry, per-request HTTP clients |

---

## Prerequisites

- Python 3.10+
- One of:
  - [Kiro IDE](https://kiro.dev/) logged in (creates `~/.aws/sso/cache/kiro-auth-token.json`), **or**
  - [Kiro CLI](https://kiro.dev/cli/) with AWS SSO (free Builder ID or corporate account)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/Shyamnath-Sankar/kiro-gateway-for-claude-code.git
cd kiro-gateway-for-claude-code

# 2. Install
pip install -r requirements.txt

# 3. Configure (or run: python setup_claude_code.py)
cp .env.example .env
# Edit .env: set PROXY_API_KEY to a secret YOU invent,
# and KIRO_CREDS_FILE to your Kiro credentials file.

# 4. Start
python main.py
# Server at http://localhost:8000
```

`setup_claude_code.py` automates step 3: it generates a `PROXY_API_KEY`,
auto-detects your Kiro credentials file, and prints the exact exports for step 5.

---

## Connect Claude Code (step 5)

Point Claude Code at the gateway with two environment variables.
`PROXY_API_KEY` is the secret you put in `.env` — Claude Code sends it as the API key.

**Linux / macOS:**

```bash
export ANTHROPIC_BASE_URL="http://localhost:8000"
export ANTHROPIC_API_KEY="your-PROXY_API_KEY-from-.env"
export ANTHROPIC_MODEL="claude-sonnet-4-5"
# Optional small/fast model for background tasks:
export ANTHROPIC_SMALL_FAST_MODEL="claude-haiku-4-5"
claude
```

**Windows PowerShell:**

```powershell
$env:ANTHROPIC_BASE_URL="http://localhost:8000"
$env:ANTHROPIC_API_KEY="your-PROXY_API_KEY-from-.env"
$env:ANTHROPIC_MODEL="claude-sonnet-4-5"
claude
```

**Or persist in `~/.claude/settings.json`:**

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8000",
    "ANTHROPIC_API_KEY": "your-PROXY_API_KEY-from-.env",
    "ANTHROPIC_MODEL": "claude-sonnet-4-5",
    "ANTHROPIC_SMALL_FAST_MODEL": "claude-haiku-4-5"
  }
}
```

### Pick a model

Use whatever your Kiro tier actually offers (free tier commonly: Sonnet 4.5, Haiku 4.5,
Sonnet 4, GLM-5, DeepSeek-V3.2, MiniMax M2.x, Qwen3-Coder-Next). Check live:

```bash
curl http://localhost:8000/v1/models -H "x-api-key: YOUR_KEY"
```

> Any `claude-*` name format works (`claude-sonnet-4-5`, `claude-sonnet-4.5`,
> dated `claude-sonnet-4-5-20250929`) — names are normalized automatically.
> Unknown names pass through to Kiro, which is the final arbiter.

---

## Recommended `.env` for Claude Code

```bash
PROXY_API_KEY="invent-a-long-random-secret-here"
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"
KIRO_REGION="us-east-1"

# Claude Code sends 30+ tools — trim oldest history instead of failing:
AUTO_TRIM_PAYLOAD="true"

LOG_LEVEL="INFO"
# When something breaks, switch to errors and check debug_logs/:
# DEBUG_MODE="errors"
```

---

## Verify it works

```bash
# 1. Gateway health
curl http://localhost:8000/v1/models -H "x-api-key: YOUR_KEY"

# 2. Non-streaming message
curl http://localhost:8000/v1/messages \
  -H "x-api-key: YOUR_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5","max_tokens":64,
       "messages":[{"role":"user","content":"Reply with: gateway ok"}]}'

# 3. In Claude Code: ask it anything, then check compaction works on long sessions.
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Improperly formed request` (400) | Payload too large / tool quirks. Keep `AUTO_TRIM_PAYLOAD=true`. If it persists, set `DEBUG_MODE="errors"`, reproduce, inspect `debug_logs/`. |
| Empty replies after `CONTINUE`, `429` warnings in gateway log | Kiro rate limit on that model. Wait a minute, retry, or switch `ANTHROPIC_MODEL` to a cached model from `/v1/models`. Single-account setups have no failover; see upstream docs for `ACCOUNT_SYSTEM=true` multi-account. |
| `401 Invalid API key` | `ANTHROPIC_API_KEY` must exactly equal `PROXY_API_KEY` in `.env`. |
| Port `8000` busy | `python main.py --port 9000` and use `ANTHROPIC_BASE_URL="http://localhost:9000"`. |
| Token expired / `403` loop | Gateway refreshes automatically. If it loops, re-login to Kiro IDE / `kiro-cli` so the credentials file is fresh, then restart. |
| VPN / corporate / restricted network | Set `VPN_PROXY_URL="http://127.0.0.1:7890"` (HTTP or `socks5://`) in `.env`. |

---

## Running tests

```bash
pytest -q
pytest tests/unit/test_routes_anthropic.py tests/unit/test_converters_anthropic.py -q
```

---

## Credits & license

- Upstream project: [@Jwadow/kiro-gateway](https://github.com/Jwadow/kiro-gateway) — all gateway logic, multi-language docs in `docs/`, and architecture notes belong to it.
- This fork adds: Claude Code quickstart (this file), `AGENTS.md` Section 0 auto-setup, `setup_claude_code.py`, in-message `system` role support, and Claude Code-friendly defaults.
- License: **AGPL-3.0** — see [LICENSE](LICENSE). Forks must preserve attribution and license.
