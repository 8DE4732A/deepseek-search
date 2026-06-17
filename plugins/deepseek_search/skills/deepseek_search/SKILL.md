---
name: deepseek_search
description: Use DeepSeek API-backed web search for current web information, recent docs, versions, prices, announcements, or explicit web search requests. Returns cited results through a local uv Python CLI.
---

# DeepSeek Search

Use this skill when the user asks for web search, online/current information, recent documentation, versions, pricing, announcements, news, or any answer that could be stale without checking the web.

Do not use this skill for purely local codebase questions or for private/authenticated pages unless the user has provided a public URL or accessible source.

## CLI command

From the repository root, run:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} src/deepseek_search.py --json --query "<specific search query>"
```

If the console script is available, this equivalent command is also valid from `plugins/deepseek_search`:

```bash
uv run deepseek-search --json --query "<specific search query>"
```

Use `--markdown` only when you want human-readable output. Prefer `--json` when you need to parse the answer and citations.

## Query guidance

- Make the query specific: include product names, version numbers, dates, and the exact topic.
- If results are weak or missing, reformulate and search again instead of filling gaps from memory.
- Preserve source URLs from the CLI output in your final answer.
- If the CLI reports missing credentials or config, tell the user to configure `~/.deepseek` or set `DEEPSEEK_API_KEY` / `ANTHROPIC_AUTH_TOKEN`; do not answer from memory.

## Configuration

The CLI reads DeepSeek configuration from:

- `~/.deepseek/config.json` for non-sensitive defaults.
- `~/.deepseek/credentials.json` for the API key.
- Environment overrides such as `DEEPSEEK_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `DEEPSEEK_MODEL`, and `DEEPSEEK_BASE_URL`.

Create a default config with:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} src/deepseek_search.py --init
```

Then create `~/.deepseek/credentials.json` manually:

```json
{
  "api_key": "YOUR_DEEPSEEK_API_KEY"
}
```

On Unix-like systems, recommend:

```bash
chmod 600 ~/.deepseek/credentials.json
```

## Interpreting output

The JSON output contains:

- `answer`: model-generated answer grounded in web search.
- `citations`: extracted source URLs/titles/snippets when available.
- `warnings`: compatibility or completeness notes.
- `usage`, `model`, `request_id`, and `stop_reason`: debugging metadata.

Base your response on `answer` and `citations`. If `warnings` says the result is incomplete, say that plainly.
