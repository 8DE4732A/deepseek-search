"""DeepSeek Anthropic-compatible web search CLI."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

DEFAULT_BASE_URL = "https://api.deepseek.com/anthropic"
DEFAULT_MODEL = "deepseek-v4-pro[1m]"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_USES = 5
DEFAULT_WEB_SEARCH_TOOL_TYPE = "web_search_20260209"
DEFAULT_OUTPUT_FORMAT = "json"
MAX_CONTINUATIONS = 3


class CliError(Exception):
    """A user-facing CLI error with a process exit code."""

    def __init__(self, message: str, exit_code: int = 1, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.detail = detail


@dataclass(frozen=True)
class Settings:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    web_search_tool_type: str = DEFAULT_WEB_SEARCH_TOOL_TYPE
    max_uses: int = DEFAULT_MAX_USES
    allowed_domains: tuple[str, ...] = ()
    blocked_domains: tuple[str, ...] = ()
    output_format: str = DEFAULT_OUTPUT_FORMAT
    verbose: bool = False
    warnings: tuple[str, ...] = ()


def config_dir() -> Path:
    override = os.environ.get("DEEPSEEK_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".deepseek"


def default_config() -> dict[str, Any]:
    return {
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "timeout_seconds": int(DEFAULT_TIMEOUT_SECONDS),
        "max_retries": DEFAULT_MAX_RETRIES,
        "web_search_tool_type": DEFAULT_WEB_SEARCH_TOOL_TYPE,
        "search": {
            "max_uses": DEFAULT_MAX_USES,
            "allowed_domains": [],
            "blocked_domains": [],
        },
        "output_format": DEFAULT_OUTPUT_FORMAT,
    }


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid JSON in {path}: {exc}", 1) from exc
    if not isinstance(data, dict):
        raise CliError(f"Invalid JSON in {path}: top-level value must be an object", 1)
    return data


def write_initial_config(directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    cfg_path = directory / "config.json"
    if cfg_path.exists():
        return f"Config already exists: {cfg_path}"
    cfg_path.write_text(json.dumps(default_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return (
        f"Created {cfg_path}. Put your API key in {directory / 'credentials.json'} "
        "or set DEEPSEEK_API_KEY / ANTHROPIC_AUTH_TOKEN."
    )


def parse_domain_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def require_str(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise CliError(f"Config field {key!r} must be a string", 1)
    return value


def require_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CliError(f"Config field {key!r} must be an integer", 1) from exc


def require_float(data: dict[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CliError(f"Config field {key!r} must be a number", 1) from exc


def require_list(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CliError(f"Config field {key!r} must be a list of strings", 1)
    return tuple(item for item in value if item)


def credentials_permission_warning(path: Path) -> str | None:
    if not path.exists() or os.name == "nt":
        return None
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        return f"{path} is readable by group/others; recommended permissions are 0600."
    return None


def load_settings(args: argparse.Namespace) -> Settings:
    directory = config_dir()
    cfg_path = directory / "config.json"
    cred_path = directory / "credentials.json"

    config = read_json_file(cfg_path)
    credentials = read_json_file(cred_path)
    search_config = config.get("search", {})
    if search_config is None:
        search_config = {}
    if not isinstance(search_config, dict):
        raise CliError("Config field 'search' must be an object", 1)

    warnings: list[str] = []
    permission_warning = credentials_permission_warning(cred_path)
    if permission_warning:
        warnings.append(permission_warning)

    settings = Settings(
        base_url=require_str(config, "base_url", DEFAULT_BASE_URL),
        model=require_str(config, "model", DEFAULT_MODEL),
        api_key=credentials.get("api_key") if isinstance(credentials.get("api_key"), str) else None,
        max_tokens=require_int(config, "max_tokens", DEFAULT_MAX_TOKENS),
        timeout_seconds=require_float(config, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        max_retries=require_int(config, "max_retries", DEFAULT_MAX_RETRIES),
        web_search_tool_type=require_str(config, "web_search_tool_type", DEFAULT_WEB_SEARCH_TOOL_TYPE),
        max_uses=require_int(search_config, "max_uses", DEFAULT_MAX_USES),
        allowed_domains=require_list(search_config, "allowed_domains"),
        blocked_domains=require_list(search_config, "blocked_domains"),
        output_format=require_str(config, "output_format", DEFAULT_OUTPUT_FORMAT),
        warnings=tuple(warnings),
    )

    env_api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if env_api_key:
        settings = replace(settings, api_key=env_api_key)
    if os.environ.get("DEEPSEEK_BASE_URL"):
        settings = replace(settings, base_url=os.environ["DEEPSEEK_BASE_URL"])
    if os.environ.get("DEEPSEEK_MODEL") or os.environ.get("ANTHROPIC_MODEL"):
        settings = replace(settings, model=os.environ.get("DEEPSEEK_MODEL") or os.environ["ANTHROPIC_MODEL"])
    if os.environ.get("DEEPSEEK_TIMEOUT"):
        settings = replace(settings, timeout_seconds=float(os.environ["DEEPSEEK_TIMEOUT"]))
    if os.environ.get("DEEPSEEK_MAX_RETRIES"):
        settings = replace(settings, max_retries=int(os.environ["DEEPSEEK_MAX_RETRIES"]))
    if os.environ.get("DEEPSEEK_ALLOWED_DOMAINS"):
        settings = replace(settings, allowed_domains=parse_domain_list(os.environ.get("DEEPSEEK_ALLOWED_DOMAINS")))
    if os.environ.get("DEEPSEEK_BLOCKED_DOMAINS"):
        settings = replace(settings, blocked_domains=parse_domain_list(os.environ.get("DEEPSEEK_BLOCKED_DOMAINS")))

    if args.model:
        settings = replace(settings, model=args.model)
    if args.base_url:
        settings = replace(settings, base_url=args.base_url)
    if args.max_tokens is not None:
        settings = replace(settings, max_tokens=args.max_tokens)
    if args.timeout is not None:
        settings = replace(settings, timeout_seconds=args.timeout)
    if args.max_retries is not None:
        settings = replace(settings, max_retries=args.max_retries)
    if args.web_search_tool_type:
        settings = replace(settings, web_search_tool_type=args.web_search_tool_type)
    if args.max_uses is not None:
        settings = replace(settings, max_uses=args.max_uses)
    if args.allowed_domain:
        settings = replace(settings, allowed_domains=tuple(args.allowed_domain))
    if args.blocked_domain:
        settings = replace(settings, blocked_domains=tuple(args.blocked_domain))
    if args.output_format:
        settings = replace(settings, output_format=args.output_format)
    if args.verbose:
        settings = replace(settings, verbose=True)

    if settings.output_format not in {"json", "markdown", "raw"}:
        raise CliError("output_format must be one of: json, markdown, raw", 1)
    if settings.max_tokens <= 0:
        raise CliError("max_tokens must be positive", 1)
    if settings.max_uses <= 0:
        raise CliError("max_uses must be positive", 1)
    if not settings.api_key:
        raise CliError(
            "Missing DeepSeek API key. Set DEEPSEEK_API_KEY or ANTHROPIC_AUTH_TOKEN, "
            f"or create {cred_path} with {json.dumps({'api_key': 'YOUR_DEEPSEEK_API_KEY'})}.",
            2,
        )
    return settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deepseek-search",
        description="Search the web through DeepSeek's Anthropic-compatible API.",
    )
    parser.add_argument("query_parts", nargs="*", help="Search query text")
    parser.add_argument("-q", "--query", help="Search query text")
    parser.add_argument("--init", action="store_true", help="Create ~/.deepseek/config.json if it does not exist")
    parser.add_argument("--model", help=f"Model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--base-url", help=f"Anthropic-compatible base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--max-tokens", type=int, help=f"Maximum answer tokens (default: {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--timeout", type=float, help=f"Request timeout in seconds (default: {int(DEFAULT_TIMEOUT_SECONDS)})")
    parser.add_argument("--max-retries", type=int, help=f"SDK retry count (default: {DEFAULT_MAX_RETRIES})")
    parser.add_argument("--web-search-tool-type", help=f"Server-side web search tool type (default: {DEFAULT_WEB_SEARCH_TOOL_TYPE})")
    parser.add_argument("--max-uses", type=int, help=f"Maximum web_search tool uses (default: {DEFAULT_MAX_USES})")
    parser.add_argument("--allowed-domain", action="append", help="Restrict search to a domain; can be repeated")
    parser.add_argument("--blocked-domain", action="append", help="Block a search domain; can be repeated")
    parser.add_argument("--verbose", action="store_true", help="Print request metadata to stderr")

    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", dest="output_format", action="store_const", const="json", help="Print structured JSON")
    output.add_argument("--markdown", dest="output_format", action="store_const", const="markdown", help="Print Markdown")
    output.add_argument("--raw", dest="output_format", action="store_const", const="raw", help="Print raw API response JSON")
    return parser


def resolve_query(args: argparse.Namespace) -> str:
    positional_query = " ".join(args.query_parts).strip()
    flag_query = (args.query or "").strip()
    if positional_query and flag_query:
        raise CliError("Pass the query either positionally or with --query, not both", 1)
    query = flag_query or positional_query
    if not query:
        raise CliError("Missing search query", 1)
    return query


def normalize(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return normalize(value.to_dict())
    if hasattr(value, "model_dump"):
        return normalize(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_web_search_tool(settings: Settings) -> dict[str, Any]:
    tool: dict[str, Any] = {
        "type": settings.web_search_tool_type,
        "name": "web_search",
        "max_uses": settings.max_uses,
    }
    if settings.allowed_domains:
        tool["allowed_domains"] = list(settings.allowed_domains)
    if settings.blocked_domains:
        tool["blocked_domains"] = list(settings.blocked_domains)
    return tool


def create_client(settings: Settings) -> Any:
    try:
        import anthropic
    except ImportError as exc:
        raise CliError("Missing dependency 'anthropic'. Run this command through uv from the plugin directory.", 1) from exc

    try:
        return anthropic.Anthropic(
            base_url=settings.base_url,
            auth_token=settings.api_key,
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
    except TypeError:
        os.environ["ANTHROPIC_BASE_URL"] = settings.base_url
        os.environ["ANTHROPIC_AUTH_TOKEN"] = settings.api_key or ""
        return anthropic.Anthropic(timeout=settings.timeout_seconds, max_retries=settings.max_retries)


def is_tool_choice_unsupported(exc: Exception) -> bool:
    message = str(exc).lower()
    return "tool_choice" in message and ("unsupported" in message or "unknown" in message or "invalid" in message)


def is_web_search_unsupported(exc: Exception) -> bool:
    message = str(exc).lower()
    return "web_search" in message or "web search" in message or "tools" in message


def create_message(client: Any, params: dict[str, Any]) -> Any:
    return client.messages.create(**params)


def search(client: Any, settings: Settings, query: str) -> dict[str, Any]:
    warnings = list(settings.warnings)
    messages: list[dict[str, Any]] = [{"role": "user", "content": query}]
    params: dict[str, Any] = {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "system": (
            "You are a web search assistant. Use web_search to answer the user's "
            "question with concise grounded information and cite sources. If the "
            "search results are insufficient, say so explicitly."
        ),
        "messages": messages,
        "tools": [build_web_search_tool(settings)],
        "tool_choice": {"type": "tool", "name": "web_search"},
    }

    response: Any | None = None
    for _ in range(MAX_CONTINUATIONS + 1):
        try:
            response = create_message(client, params)
        except Exception as exc:  # noqa: BLE001 - classify SDK exceptions below without importing globally.
            if "tool_choice" in params and is_tool_choice_unsupported(exc):
                warnings.append("DeepSeek rejected tool_choice; retried once without forcing web_search.")
                params.pop("tool_choice", None)
                response = create_message(client, params)
            elif is_web_search_unsupported(exc):
                raise CliError(
                    "The DeepSeek Anthropic-compatible endpoint rejected the web_search request shape.",
                    4,
                    detail=str(exc),
                ) from exc
            else:
                raise

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "pause_turn":
            warnings.append("API returned pause_turn; continued the server-side web_search turn.")
            messages.append({"role": "assistant", "content": getattr(response, "content", [])})
            params["messages"] = messages
            params.pop("tool_choice", None)
            continue
        break

    if response is None:
        raise CliError("No response returned from API", 3)

    envelope = build_envelope(response, query, warnings, settings)
    stop_reason = envelope.get("stop_reason")
    if stop_reason == "refusal":
        envelope["warnings"].append("Model returned stop_reason=refusal; answer may be empty or partial.")
    elif stop_reason == "max_tokens":
        envelope["warnings"].append("Model hit max_tokens; rerun with --max-tokens for a complete answer.")
    elif not envelope.get("answer"):
        envelope["warnings"].append("No text answer was returned; inspect --raw for response details.")
    return envelope


def build_envelope(response: Any, query: str, warnings: list[str], settings: Settings) -> dict[str, Any]:
    raw = normalize(response)
    content = raw.get("content", []) if isinstance(raw, dict) else []
    answer = extract_answer(content)
    citations = extract_citations(content)
    usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
    return {
        "query": query,
        "answer": answer,
        "citations": citations,
        "usage": usage if isinstance(usage, dict) else {},
        "model": raw.get("model", settings.model) if isinstance(raw, dict) else settings.model,
        "request_id": getattr(response, "_request_id", None) or (raw.get("request_id") if isinstance(raw, dict) else None),
        "stop_reason": raw.get("stop_reason") if isinstance(raw, dict) else getattr(response, "stop_reason", None),
        "warnings": warnings,
        "raw_response": raw,
    }


def extract_answer(content: Iterable[Any]) -> str:
    parts: list[str] = []
    for block in content:
        block_dict = block if isinstance(block, dict) else normalize(block)
        if isinstance(block_dict, dict) and block_dict.get("type") == "text" and isinstance(block_dict.get("text"), str):
            parts.append(block_dict["text"])
    return "\n".join(part.strip() for part in parts if part.strip()).strip()


def shorten(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def extract_citations(content: Iterable[Any]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_candidate(item: dict[str, Any]) -> None:
        url = item.get("url") or item.get("uri")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return
        if url in seen:
            return
        seen.add(url)
        title = item.get("title") or item.get("name") or item.get("source") or url
        snippet = item.get("snippet") or item.get("cited_text") or item.get("text") or item.get("content") or ""
        citations.append({"title": shorten(title, 160), "url": url, "snippet": shorten(snippet)})

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            add_candidate(value)
            for key in ("citations", "results", "content", "items", "data"):
                if key in value:
                    walk(value[key])
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(list(content))
    return citations


def render_json(envelope: dict[str, Any]) -> str:
    public_envelope = {key: value for key, value in envelope.items() if key != "raw_response"}
    return json.dumps(public_envelope, ensure_ascii=False, indent=2)


def render_raw(envelope: dict[str, Any]) -> str:
    return json.dumps(envelope.get("raw_response", {}), ensure_ascii=False, indent=2)


def render_markdown(envelope: dict[str, Any]) -> str:
    lines: list[str] = []
    if envelope.get("answer"):
        lines.append(str(envelope["answer"]).strip())
    else:
        lines.append("未返回可用答案。")

    citations = envelope.get("citations") or []
    if citations:
        lines.extend(["", "## Sources"])
        for index, citation in enumerate(citations, start=1):
            title = citation.get("title") or citation.get("url")
            url = citation.get("url")
            snippet = citation.get("snippet")
            line = f"{index}. [{title}]({url})"
            if snippet:
                line += f" — {snippet}"
            lines.append(line)

    warnings = envelope.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines).strip() + "\n"


def print_verbose(envelope: dict[str, Any]) -> None:
    metadata = {
        "model": envelope.get("model"),
        "request_id": envelope.get("request_id"),
        "stop_reason": envelope.get("stop_reason"),
        "usage": envelope.get("usage"),
    }
    print(json.dumps(metadata, ensure_ascii=False), file=sys.stderr)


def classify_unhandled_exception(exc: Exception) -> CliError:
    try:
        import anthropic
    except ImportError:
        return CliError(str(exc), 3)

    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return CliError("DeepSeek authentication failed. Check DEEPSEEK_API_KEY, ANTHROPIC_AUTH_TOKEN, or ~/.deepseek/credentials.json.", 2, detail=str(exc))
    if isinstance(exc, anthropic.BadRequestError):
        exit_code = 4 if is_web_search_unsupported(exc) or is_tool_choice_unsupported(exc) else 3
        return CliError("API rejected the request.", exit_code, detail=str(exc))
    if isinstance(exc, anthropic.RateLimitError):
        retry_after = None
        response = getattr(exc, "response", None)
        if response is not None:
            retry_after = response.headers.get("retry-after")
        detail = f"Retry after {retry_after}s. {exc}" if retry_after else str(exc)
        return CliError("DeepSeek rate limit exceeded.", 3, detail=detail)
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return CliError("Network error while contacting DeepSeek.", 3, detail=str(exc))
    if isinstance(exc, anthropic.APIStatusError):
        return CliError(f"DeepSeek API error: HTTP {exc.status_code}.", 3, detail=str(exc))
    return CliError(str(exc), 3)


def render_error(error: CliError, output_format: str | None) -> str:
    if output_format == "json":
        payload = {"error": error.message, "detail": error.detail, "exit_code": error.exit_code}
        return json.dumps(payload, ensure_ascii=False, indent=2)
    detail = f"\n{error.detail}" if error.detail else ""
    return f"Error: {error.message}{detail}"


def run(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_format = args.output_format or DEFAULT_OUTPUT_FORMAT
    try:
        if args.init:
            print(write_initial_config(config_dir()))
            if not args.query and not args.query_parts:
                return 0

        query = resolve_query(args)
        settings = load_settings(args)
        output_format = settings.output_format
        api_client = client or create_client(settings)
        envelope = search(api_client, settings, query)
        if settings.verbose:
            print_verbose(envelope)

        if settings.output_format == "raw":
            print(render_raw(envelope))
        elif settings.output_format == "markdown":
            print(render_markdown(envelope), end="")
        else:
            print(render_json(envelope))
        return 0
    except CliError as exc:
        print(render_error(exc, output_format), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001 - last-resort CLI classification.
        error = classify_unhandled_exception(exc)
        print(render_error(error, output_format), file=sys.stderr)
        return error.exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
