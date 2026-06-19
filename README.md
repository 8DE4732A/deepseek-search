# DeepSeek Search

DeepSeek Search is a Claude Code plugin that wraps DeepSeek's Anthropic-compatible Web Search capability as a local Python CLI and exposes it through a Claude Code skill.

## What it provides

- A `deepseek-search` CLI (Python + [`uv`](https://docs.astral.sh/uv/)), [published on PyPI](https://pypi.org/project/deepseek-search/).
- DeepSeek API configuration under `~/.deepseek`.
- A Claude Code skill at `plugins/deepseek_search/skills/deepseek_search/SKILL.md` that tells Claude Code when and how to call the CLI.

## Project layout

```text
.claude-plugin/marketplace.json
.github/workflows/          # CI + publish-to-PyPI on `v*` tags
plugins/deepseek_search/    # Claude Code plugin manifest + skill
  .claude-plugin/plugin.json
  skills/deepseek_search/SKILL.md
src/deepseek_search.py      # CLI implementation
tests/test_deepseek_search.py
pyproject.toml
uv.lock
```

The Python package lives at the repository root; `plugins/deepseek_search/` holds only the Claude Code plugin manifest and skill instructions.

## Install

The recommended way to use the CLI is as a global `uv` tool:

```bash
uv tool install deepseek-search
```

Then `deepseek-search` is available on `PATH` everywhere.

### From source (development)

```bash
git clone https://github.com/8DE4732A/deepseek-search.git
cd deepseek-search
uv sync --dev            # install dependencies
uv run pytest            # run tests (no API key required)
```

## Configure DeepSeek

All configuration lives under `~/.deepseek` and is managed through the `config` subcommand. There are **no environment variables** — settings come from the config files or one-off CLI flags.

```bash
deepseek-search config init                                    # write a default config.json
deepseek-search config set api_key YOUR_DEEPSEEK_API_KEY       # stored in ~/.deepseek/credentials.json (chmod 600)
deepseek-search config set model deepseek-v4-pro[1m]           # set any field
deepseek-search config get model                               # read a single value
deepseek-search config list                                    # show full effective config (api_key masked)
```

Configurable keys (type-coerced automatically):

| Key | Stored in | Type |
|---|---|---|
| `api_key` | `credentials.json` | string (chmod 600) |
| `base_url`, `model`, `web_search_tool_type`, `output_format` | `config.json` | string |
| `max_tokens`, `max_retries` | `config.json` | int |
| `timeout_seconds` | `config.json` | float |
| `max_uses`, `allowed_domains`, `blocked_domains` | `config.json` (`search.*`) | int / comma-list |

Advanced search flags (`--model`, `--max-tokens`, `--timeout`, `--max-uses`, `--allowed-domain`, `--blocked-domain`, …) override `config.json` for a single run without writing it back.

## CLI usage

```bash
deepseek-search --json --query "DeepSeek Claude Code web search documentation"
deepseek-search "DeepSeek API Claude Code integration"        # bare positional query also works
deepseek-search search --markdown "DeepSeek API Claude Code integration"
deepseek-search --help
```

The JSON output includes:

- `answer`
- `citations`
- `warnings`
- `usage`
- `model`
- `request_id`
- `stop_reason`

## Releasing / publishing

Releases are produced automatically by the **Publish to PyPI** GitHub Action whenever a `v*` git tag is pushed:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Prerequisites (one-time, in the GitHub repo + PyPI):

1. Register the project as a **Trusted Publisher** on PyPI:
   - PyPI publishing environment: `pypi`
   - GitHub repository: `8DE4732A/deepseek-search`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
2. No PyPI API token is required — publishing uses OIDC.

The package version is derived from the git tag via `setuptools-scm`, so the workflow fails fast if the tag and the built version disagree.

## License

MIT License. See [LICENSE](LICENSE).
