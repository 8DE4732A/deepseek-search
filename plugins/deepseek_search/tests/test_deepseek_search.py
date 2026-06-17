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


def test_load_settings_cli_overrides_env_and_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("DEEPSEEK_MODEL", "env-model")
    write_credentials(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "model": "config-model",
                "search": {"allowed_domains": ["config.example"]},
            }
        ),
        encoding="utf-8",
    )

    parser = deepseek_search.build_parser()
    args = parser.parse_args(
        [
            "--query",
            "hello",
            "--model",
            "cli-model",
            "--allowed-domain",
            "docs.deepseek.com",
        ]
    )

    settings = deepseek_search.load_settings(args)

    assert settings.model == "cli-model"
    assert settings.allowed_domains == ("docs.deepseek.com",)
    assert settings.api_key == "test-key"


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


def test_missing_api_key_returns_auth_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    code = deepseek_search.run(["--json", "--query", "hello"])

    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert code == 2
    assert "Missing DeepSeek API key" in payload["error"]


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


def test_init_writes_default_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_CONFIG_DIR", str(tmp_path))

    code = deepseek_search.run(["--init"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Created" in captured.out
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["base_url"] == "https://api.deepseek.com/anthropic"
    assert config["model"] == "deepseek-v4-pro[1m]"
