---
name: deepseek_search
description: Use DeepSeek API-backed web search for current web information, recent docs, versions, prices, announcements, or explicit web search requests. Returns cited results through a local uv Python CLI.
---

# DeepSeek Search

Use this skill when the user asks for web search, online/current information, recent documentation, versions, pricing, announcements, news, or any answer that could be stale without checking the web.

Do not use this skill for purely local codebase questions or for private/authenticated pages unless the user has provided a public URL or accessible source.

## Prerequisites (one-time install)

The `deepseek-search` CLI is a global `uv` tool, installed once per machine:

```bash
uv tool install deepseek-search
```

Installers from the [PyPI releases](https://pypi.org/project/deepseek-search/) are produced automatically when a `v*` git tag is pushed in the project repository. Once installed, `deepseek-search` is available on `PATH` everywhere (including inside this skill) — no checkout or virtualenv required.

## CLI command

```bash
deepseek-search --json --query "<specific search query>"
```

The `search` subcommand is the default, so a bare positional query also works:

```bash
deepseek-search "<specific search query>"
deepseek-search search --markdown "<specific search query>"
```

Use `--markdown` only when you want human-readable output. Prefer `--json` when you need to parse the answer and citations.

If the `deepseek-search` command is not found, ask the user to run `uv tool install deepseek-search`, then retry — do not answer from memory.

## Query guidance

- Make the query specific: include product names, version numbers, dates, and the exact topic.
- If results are weak or missing, reformulate and search again instead of filling gaps from memory.
- Preserve source URLs from the CLI output in your final answer.
- If the CLI reports missing credentials or config, tell the user to configure settings with `deepseek-search config set ...` (see below); do not answer from memory.

## Configuration

All configuration lives under `~/.deepseek`:

- `~/.deepseek/config.json` — non-sensitive settings (model, base_url, max_tokens, timeout_seconds, max_retries, web_search_tool_type, output_format, and `search.*` fields max_uses / allowed_domains / blocked_domains).
- `~/.deepseek/credentials.json` — the API key (chmod 0600).

There are **no environment variables**. Settings come from the config files or from one-off CLI flags. Manage them with the `config` subcommand:

```bash
deepseek-search config init                          # write a default config.json
deepseek-search config set model deepseek-v4-flash # set any field
deepseek-search config set api_key YOUR_DEEPSEEK_API_KEY   # stored in credentials.json, chmod 0600
deepseek-search config get model                    # read a single value
deepseek-search config list                         # show full effective config (api_key masked)
```

Keys map 1:1 to the settings above; values are type-coerced (int for max_tokens/max_uses/max_retries, float for timeout_seconds, comma-list for allowed_domains/blocked_domains). Unknown keys are rejected.

## Interpreting output

The JSON output contains:

- `answer`: model-generated answer grounded in web search.
- `citations`: extracted source URLs/titles/snippets when available.
- `warnings`: compatibility or completeness notes.
- `usage`, `model`, `request_id`, and `stop_reason`: debugging metadata.

Base your response on `answer` and `citations`. If `warnings` says the result is incomplete, say that plainly.
