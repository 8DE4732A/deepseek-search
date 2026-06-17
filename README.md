# DeepSeek Search

DeepSeek Search is a Claude Code plugin that wraps DeepSeek's Anthropic-compatible Web Search capability as a local Python CLI and exposes it through a Claude Code skill.

## What it provides

- A `deepseek-search` CLI implemented with Python and `uv`.
- DeepSeek API configuration under `~/.deepseek`.
- A Claude Code skill at `plugins/deepseek_search/skills/deepseek_search/SKILL.md` that tells Claude Code when and how to call the CLI.

## Project layout

```text
.claude-plugin/marketplace.json
plugins/deepseek_search/
  .claude-plugin/plugin.json
  pyproject.toml
  src/deepseek_search.py
  skills/deepseek_search/SKILL.md
  tests/test_deepseek_search.py
```

## Setup

Install dependencies through `uv` from the plugin directory:

```bash
cd plugins/deepseek_search
uv sync
```

Create a default DeepSeek config:

```bash
uv run src/deepseek_search.py --init
```

Then create `~/.deepseek/credentials.json`:

```json
{
  "api_key": "YOUR_DEEPSEEK_API_KEY"
}
```

Recommended permissions on Unix-like systems:

```bash
chmod 600 ~/.deepseek/credentials.json
```

You can also provide credentials through environment variables:

- `DEEPSEEK_API_KEY`
- `ANTHROPIC_AUTH_TOKEN`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`

## CLI usage

From `plugins/deepseek_search`:

```bash
uv run src/deepseek_search.py --json --query "DeepSeek Claude Code web search documentation"
uv run deepseek-search --markdown --query "DeepSeek API Claude Code integration"
```

Useful options:

```bash
uv run deepseek-search --help
```

The JSON output includes:

- `answer`
- `citations`
- `warnings`
- `usage`
- `model`
- `request_id`
- `stop_reason`

## Testing

```bash
cd plugins/deepseek_search
uv run pytest
```

The tests use mocked responses and do not require a real DeepSeek API key.

## License

MIT License. See [LICENSE](LICENSE).
