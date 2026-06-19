import json

import deepseek_search


class FakeResponse:
    def __init__(self, raw):
        self._raw = raw
        self.content = raw.get("content", [])
        self.stop_reason = raw.get("stop_reason")
        self._request_id = raw.get("request_id")

    def to_dict(self):
        return self._raw


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def write_credentials(path, api_key="test-key"):
    path.mkdir(parents=True, exist_ok=True)
    (path / "credentials.json").write_text(json.dumps({"api_key": api_key}), encoding="utf-8")


def write_config(path, data):
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Settings loading
# ---------------------------------------------------------------------------


def test_load_settings_cli_overrides_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_credentials(tmp_path)
    write_config(
        tmp_path,
        {
            "model": "config-model",
            "search": {"allowed_domains": ["config.example"]},
        },
    )

    parser = deepseek_search.build_parser()
    args = parser.parse_args(
        deepseek_search.inject_default_subcommand(
            ["--query", "hello", "--model", "cli-model", "--allowed-domain", "docs.deepseek.com"]
        )
    )

    settings = deepseek_search.load_settings(args)

    assert settings.model == "cli-model"
    assert settings.allowed_domains == ("docs.deepseek.com",)
    assert settings.api_key == "test-key"


def test_load_settings_has_no_env_var_overrides(tmp_path, monkeypatch):
    """Environment variables must not influence settings anymore."""
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_credentials(tmp_path, api_key="cred-key")
    write_config(tmp_path, {"model": "config-model"})
    # These must be ignored.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ignored-env-key")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ignored-env-token")
    monkeypatch.setenv("DEEPSEEK_MODEL", "ignored-env-model")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://ignored.example")

    parser = deepseek_search.build_parser()
    args = parser.parse_args(deepseek_search.inject_default_subcommand(["--query", "hi"]))

    settings = deepseek_search.load_settings(args)
    assert settings.api_key == "cred-key"
    assert settings.model == "config-model"
    assert settings.base_url == "https://api.deepseek.com/anthropic"


# ---------------------------------------------------------------------------
# Search run (uses the default subcommand routing)
# ---------------------------------------------------------------------------


def test_run_with_fake_client_outputs_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_credentials(tmp_path)
    response = FakeResponse(
        {
            "id": "msg_test",
            "model": "deepseek-v4-pro[1m]",
            "stop_reason": "end_turn",
            "content": [
                {
                    "type": "text",
                    "text": "DeepSeek supports Claude Code web search.",
                    "citations": [
                        {
                            "title": "DeepSeek docs",
                            "url": "https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code",
                            "cited_text": "Claude Code search is supported.",
                        }
                    ],
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 20},
            "request_id": "req_test",
        }
    )
    client = FakeClient(response)

    code = deepseek_search.run(["--json", "--query", "DeepSeek Claude Code search"], client=client)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["answer"] == "DeepSeek supports Claude Code web search."
    assert payload["citations"][0]["url"].startswith("https://api-docs.deepseek.com")
    assert payload["request_id"] == "req_test"
    assert "raw_response" not in payload
    assert client.messages.calls[0]["tools"][0]["type"] == "web_search_20260209"
    assert client.messages.calls[0]["tool_choice"] == {"type": "tool", "name": "web_search"}


def test_run_positional_query_routes_to_search(tmp_path, monkeypatch, capsys):
    """Bare positional query (no subcommand) should still search."""
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_credentials(tmp_path)
    response = FakeResponse(
        {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {},
        }
    )
    client = FakeClient(response)

    code = deepseek_search.run(["positional query here"], client=client)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "positional query here"
    assert payload["answer"] == "ok"


def test_missing_api_key_returns_auth_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))

    code = deepseek_search.run(["--json", "--query", "hello"])

    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert code == 2
    assert "Missing DeepSeek API key" in payload["error"]
    assert "config set api_key" in payload["error"]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_markdown_includes_sources_and_warnings():
    markdown = deepseek_search.render_markdown(
        {
            "answer": "Answer text.",
            "citations": [
                {"title": "Example", "url": "https://example.com", "snippet": "Snippet"}
            ],
            "warnings": ["careful"],
        }
    )

    assert "Answer text." in markdown
    assert "[Example](https://example.com)" in markdown
    assert "## Warnings" in markdown
    assert "careful" in markdown


# ---------------------------------------------------------------------------
# config init
# ---------------------------------------------------------------------------


def test_config_init_writes_default_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))

    code = deepseek_search.run(["config", "init"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Created" in captured.out
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["base_url"] == "https://api.deepseek.com/anthropic"
    assert config["model"] == "deepseek-v4-pro[1m]"


def test_config_init_is_idempotent_without_force(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, {"model": "custom"})

    code = deepseek_search.run(["config", "init"])

    assert code == 0
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["model"] == "custom"  # not overwritten
    assert "already exists" in capsys.readouterr().out


def test_config_init_force_overwrites(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, {"model": "custom"})

    code = deepseek_search.run(["config", "init", "--force"])

    assert code == 0
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["model"] == "deepseek-v4-pro[1m]"  # reset to default


# ---------------------------------------------------------------------------
# config set / get / list
# ---------------------------------------------------------------------------


def test_config_set_writes_top_level_field(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())

    code = deepseek_search.run(["config", "set", "model", "custom-model"])

    assert code == 0
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["model"] == "custom-model"
    # other keys preserved
    assert config["base_url"] == "https://api.deepseek.com/anthropic"


def test_config_set_coerces_int_and_float(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())

    assert deepseek_search.run(["config", "set", "max_tokens", "8192"]) == 0
    assert deepseek_search.run(["config", "set", "timeout_seconds", "30.5"]) == 0

    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["max_tokens"] == 8192
    assert config["timeout_seconds"] == 30.5


def test_config_set_invalid_int_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())

    code = deepseek_search.run(["config", "set", "max_tokens", "not-a-number"])

    assert code == 1
    assert "max_tokens" in capsys.readouterr().err


def test_config_set_search_field_writes_nested(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())

    code = deepseek_search.run(["config", "set", "allowed_domains", "a.com,b.com"])

    assert code == 0
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["search"]["allowed_domains"] == ["a.com", "b.com"]


def test_config_set_api_key_routes_to_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())

    code = deepseek_search.run(["config", "set", "api_key", "sk-secret"])

    assert code == 0
    credentials = json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))
    assert credentials["api_key"] == "sk-secret"
    # api_key must NOT leak into config.json
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert "api_key" not in config


def test_config_set_unknown_key_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())

    code = deepseek_search.run(["config", "set", "nonexistent", "x"])

    assert code == 1
    assert "Unknown config key" in capsys.readouterr().err


def test_config_get_returns_value(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, {**deepseek_search.default_config(), "model": "got-model"})

    code = deepseek_search.run(["config", "get", "model"])

    assert code == 0
    assert capsys.readouterr().out.strip() == '"got-model"'


def test_config_get_api_key_is_masked(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())
    write_credentials(tmp_path, api_key="sk-secret")

    code = deepseek_search.run(["config", "get", "api_key"])

    assert code == 0
    assert capsys.readouterr().out.strip() == '"<set>"'
    code_unset = deepseek_search.run(["config", "get", "api_key"])  # still set, sanity
    assert code_unset == 0


def test_config_get_missing_key_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    # empty config dir -> no config.json
    tmp_path.mkdir(parents=True, exist_ok=True)

    code = deepseek_search.run(["config", "get", "model"])

    assert code == 1
    assert "not set" in capsys.readouterr().err


def test_config_list_masks_api_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())
    write_credentials(tmp_path, api_key="sk-secret")

    code = deepseek_search.run(["config", "list"])

    assert code == 0
    output = capsys.readouterr().out
    assert "sk-secret" not in output
    payload = json.loads(output)
    assert payload["api_key"] == "<set>"


def test_config_set_then_load_settings_uses_new_value(tmp_path, monkeypatch):
    """End-to-end: config set persists, load_settings reads it back."""
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, deepseek_search.default_config())

    deepseek_search.run(["config", "set", "model", "persisted-model"])
    deepseek_search.run(["config", "set", "api_key", "persisted-key"])

    parser = deepseek_search.build_parser()
    args = parser.parse_args(deepseek_search.inject_default_subcommand(["--query", "hi"]))
    settings = deepseek_search.load_settings(args)
    assert settings.model == "persisted-model"
    assert settings.api_key == "persisted-key"
