from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .errors import AppError
from .usage import record_llm_usage


CODEX_TIMEOUT_SECONDS = 300
CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"


class CodexResponsesAdapter:
    """Minimal direct Responses client using credentials managed by Codex."""

    def __init__(self, auth_path: Path | None = None, post: Any = requests.post) -> None:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        self._auth_path = auth_path or codex_home / "auth.json"
        self._post = post

    def call(
        self,
        client: Any,
        model: str,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        client.account(refresh_token=True)
        token, account_id = self._credentials()
        payload = direct_responses_payload(model, messages, output_schema)
        headers = {
            "Authorization": f"Bearer {token}",
            "chatgpt-account-id": account_id,
            "originator": "novel-translator",
            "User-Agent": "NovelTranslator/experimental",
            "OpenAI-Beta": "responses=experimental",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        try:
            response = self._post(
                CODEX_RESPONSES_URL,
                headers=headers,
                json=payload,
                stream=True,
                timeout=CODEX_TIMEOUT_SECONDS,
            )
        except requests.Timeout as exc:
            raise AppError("Codex request timed out.", 502) from exc
        except requests.RequestException as exc:
            raise AppError(f"Codex request failed: {exc}", 502) from exc

        if response.status_code >= 400:
            detail = response.text[:2000]
            raise AppError(
                f"Codex request failed: HTTP {response.status_code} {detail}", 502
            )
        return parse_codex_sse(response)

    def _credentials(self) -> tuple[str, str]:
        try:
            auth = json.loads(self._auth_path.read_text(encoding="utf-8"))
            tokens = auth.get("tokens") or {}
            token = str(tokens.get("access_token") or "")
            account_id = str(tokens.get("account_id") or "")
        except (OSError, json.JSONDecodeError) as exc:
            raise AppError("Codex managed ChatGPT credentials are unavailable.", 401) from exc
        if not token or not account_id:
            raise AppError("Codex managed ChatGPT credentials are unavailable.", 401)
        return token, account_id


class CodexService:
    def __init__(self) -> None:
        self._codex: Any = None
        self._start_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._login_handle: Any = None
        self._login_status = "idle"
        self._login_error = ""
        self._models_cache: dict[str, Any] | None = None
        self._usage_cache: dict[str, Any] | None = None
        self._responses = CodexResponsesAdapter()

    def _client(self) -> Any:
        with self._start_lock:
            if self._codex is None:
                try:
                    from openai_codex import Codex

                    self._codex = Codex()
                except Exception as exc:
                    raise AppError(f"Codex SDK could not start: {exc}", 502) from exc
            return self._codex

    def close(self) -> None:
        with self._start_lock:
            client = self._codex
            self._codex = None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def auth_state(self) -> dict[str, Any]:
        try:
            response = self._client().account()
            root = response.account.root if response.account is not None else None
            signed_in = root is not None and getattr(root, "type", "") == "chatgpt"
            account = None
            if signed_in:
                plan = getattr(root, "plan_type", "")
                account = {
                    "email": str(getattr(root, "email", "")),
                    "plan": getattr(plan, "value", str(plan)),
                }
            with self._state_lock:
                status = "signed_in" if signed_in else self._login_status
                if status not in {"pending", "error"}:
                    status = "signed_in" if signed_in else "signed_out"
                error = self._login_error if status == "error" else ""
            return {
                "available": True,
                "signed_in": signed_in,
                "status": status,
                "account": account,
                "error": error,
            }
        except AppError as exc:
            return {
                "available": False,
                "signed_in": False,
                "status": "error",
                "account": None,
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "available": True,
                "signed_in": False,
                "status": "error",
                "account": None,
                "error": f"Codex account status failed: {exc}",
            }

    def start_login(self) -> dict[str, Any]:
        with self._state_lock:
            if self._login_status == "pending":
                raise AppError("ChatGPT sign-in is already pending.", 409)
        try:
            handle = self._client().login_chatgpt()
        except Exception as exc:
            raise AppError(f"Could not start ChatGPT sign-in: {exc}", 502) from exc
        with self._state_lock:
            self._login_handle = handle
            self._login_status = "pending"
            self._login_error = ""
        threading.Thread(target=self._wait_for_login, args=(handle,), daemon=True).start()
        return {"auth_url": handle.auth_url, "status": "pending"}

    def _wait_for_login(self, handle: Any) -> None:
        try:
            result = handle.wait()
            if not result.success:
                raise RuntimeError(result.error or "ChatGPT sign-in failed.")
        except Exception as exc:
            with self._state_lock:
                self._login_status = "error"
                self._login_error = str(exc)
            return
        finally:
            with self._state_lock:
                if self._login_handle is handle:
                    self._login_handle = None
        with self._state_lock:
            self._login_status = "signed_in"
            self._login_error = ""
        for refresh in (self.models, self.usage):
            try:
                refresh(refresh=True)
            except Exception:
                pass

    def logout(self) -> dict[str, Any]:
        with self._state_lock:
            handle = self._login_handle
            self._login_handle = None
        if handle is not None:
            try:
                handle.cancel()
            except Exception:
                pass
        try:
            self._client().logout()
        except Exception as exc:
            raise AppError(f"ChatGPT sign-out failed: {exc}", 502) from exc
        with self._state_lock:
            self._login_status = "signed_out"
            self._login_error = ""
            self._models_cache = None
            self._usage_cache = None
        return self.auth_state()

    def models(self, refresh: bool = False) -> dict[str, Any]:
        with self._state_lock:
            cached = self._models_cache
        if cached is not None and not refresh:
            return dict(cached)
        try:
            state = self.auth_state()
            if not state["signed_in"]:
                raise AppError("Sign in with ChatGPT before loading Codex models.", 401)
            response = self._client().models()
            models = [
                {
                    "id": item.model,
                    "name": item.display_name,
                    "description": item.description,
                    "is_default": item.is_default,
                }
                for item in response.data
                if not item.hidden
            ]
            result = {
                "models": models,
                "fetched_at": int(time.time()),
                "stale": False,
                "error": "",
            }
            with self._state_lock:
                self._models_cache = result
            return dict(result)
        except Exception as exc:
            error = str(exc)
            if cached is not None:
                stale = {**cached, "stale": True, "error": error}
                with self._state_lock:
                    self._models_cache = stale
                return dict(stale)
            if isinstance(exc, AppError):
                raise
            raise AppError(f"Codex model refresh failed: {error}", 502) from exc

    def usage(self, refresh: bool = False) -> dict[str, Any]:
        with self._state_lock:
            cached = self._usage_cache
        if cached is not None and not refresh:
            return dict(cached)
        try:
            state = self.auth_state()
            if not state["signed_in"]:
                raise AppError("Sign in with ChatGPT before loading Codex usage.", 401)
            response = self._read_rate_limits()
            snapshot = response.rate_limits
            result = {
                "available": snapshot is not None,
                "fetched_at": int(time.time()),
                "stale": False,
                "error": "",
                "plan": enum_value(snapshot.plan_type) if snapshot else None,
                "limit_name": snapshot.limit_name if snapshot else None,
                "primary": rate_limit_window(snapshot.primary) if snapshot else None,
                "secondary": rate_limit_window(snapshot.secondary) if snapshot else None,
                "rate_limit_reached_type": (
                    enum_value(snapshot.rate_limit_reached_type) if snapshot else None
                ),
                "credits": (
                    snapshot.credits.model_dump(by_alias=True) if snapshot and snapshot.credits else None
                ),
                "individual_limit": (
                    snapshot.individual_limit.model_dump(by_alias=True)
                    if snapshot and snapshot.individual_limit
                    else None
                ),
            }
            with self._state_lock:
                self._usage_cache = result
            return dict(result)
        except Exception as exc:
            error = str(exc)
            if cached is not None:
                stale = {**cached, "stale": True, "error": error}
                with self._state_lock:
                    self._usage_cache = stale
                return dict(stale)
            if isinstance(exc, AppError):
                raise
            raise AppError(f"Codex usage refresh failed: {error}", 502) from exc

    def _read_rate_limits(self) -> Any:
        # openai-codex 0.1.0b3 generates this official app-server response type,
        # but its high-level Codex wrapper does not expose the RPC yet.
        from openai_codex.generated.v2_all import GetAccountRateLimitsResponse

        return self._client()._client.request(
            "account/rateLimits/read",
            None,
            response_model=GetAccountRateLimitsResponse,
        )

    def call(
        self,
        model: str,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        model = model.strip()
        if not model:
            raise AppError("A Codex model must be selected.")
        state = self.auth_state()
        if not state["signed_in"]:
            raise AppError("Sign in with ChatGPT before using the Codex backend.", 401)
        catalog = self.models()
        if model not in {item["id"] for item in catalog["models"]}:
            raise AppError(
                f"Codex model '{model}' is unavailable. Refresh models and select another model.",
                409,
            )

        try:
            response = self._responses.call(
                self._client(), model, messages, output_schema
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(f"Codex request failed: {exc}", 502) from exc

        record_llm_usage(f"codex:{model}", response)
        try:
            self.usage(refresh=True)
        except Exception:
            pass
        return response


def direct_responses_payload(
    model: str,
    messages: list[dict[str, str]],
    output_schema: dict[str, Any],
) -> dict[str, Any]:
    instructions = "\n\n".join(
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "system"
    ) or "Return only the requested JSON."
    input_items = []
    for index, message in enumerate(messages):
        role = str(message.get("role", "user"))
        content = str(message.get("content", ""))
        if role == "system":
            continue
        if role == "assistant":
            input_items.append(
                {
                    "type": "message",
                    "id": f"msg_novel_translator_{index}",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": content,
                            "annotations": [],
                        }
                    ],
                }
            )
        else:
            input_items.append(
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": content}],
                }
            )
    return {
        "model": model,
        "store": False,
        "stream": True,
        "instructions": instructions,
        "input": input_items,
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "novel_translator_output",
                "schema": output_schema,
                "strict": False,
            },
        },
        "include": ["reasoning.encrypted_content"],
        "reasoning": {"effort": "none", "summary": "auto"},
    }


def parse_codex_sse(response: Any) -> dict[str, Any]:
    output: list[str] = []
    usage: dict[str, Any] = {}
    completed = False
    for line in response.iter_lines(decode_unicode=True):
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError("Codex returned an invalid response stream.", 502) from exc
        event_type = event.get("type")
        if event_type == "response.output_text.delta":
            output.append(str(event.get("delta", "")))
        elif event_type == "response.completed":
            completed = True
            usage = (event.get("response") or {}).get("usage") or {}
        elif event_type in {"error", "response.failed", "response.incomplete"}:
            raise AppError(f"Codex request failed: {codex_event_error(event)}", 502)
    if not completed:
        raise AppError("Codex response stream ended before completion.", 502)
    content = "".join(output)
    if not content:
        raise AppError("Codex returned no final response.", 502)
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "prompt_tokens_details": usage.get("input_tokens_details", {}),
            "completion_tokens_details": usage.get("output_tokens_details", {}),
            "cost": 0.0,
        },
    }


def codex_event_error(event: dict[str, Any]) -> str:
    error = event.get("error") or (event.get("response") or {}).get("error") or event
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or error)
    return str(error)


def rate_limit_window(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "used_percent": value.used_percent,
        "remaining_percent": max(0, min(100, 100 - value.used_percent)),
        "window_duration_mins": value.window_duration_mins,
        "resets_at": value.resets_at,
    }


def enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


_service = CodexService()


def codex_auth_state() -> dict[str, Any]:
    return _service.auth_state()


def start_codex_login() -> dict[str, Any]:
    return _service.start_login()


def logout_codex() -> dict[str, Any]:
    return _service.logout()


def codex_models(refresh: bool = False) -> dict[str, Any]:
    return _service.models(refresh)


def codex_remaining_usage(refresh: bool = False) -> dict[str, Any]:
    return _service.usage(refresh)


def call_codex(
    model: str,
    messages: list[dict[str, str]],
    output_schema: dict[str, Any],
) -> dict[str, Any]:
    return _service.call(model, messages, output_schema)


def close_codex() -> None:
    _service.close()
