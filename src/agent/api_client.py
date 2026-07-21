"""API client for the Agent backend service.

POST /chat/completions  (OpenAI-compatible)
Request:  {"model": "...", "messages": [{"role":"user","content":"..."}]}
Response: {"choices": [{"message": {"content": "..."}}]}

Features: retry (max 3), 30 s timeout, SSE streaming, categorized errors.
"""

import json
import time
from typing import Any, Generator

import requests
from requests.exceptions import ConnectionError, ReadTimeout, RequestException


# ---------------------------------------------------------------------------
# Categorised error hierarchy
# ---------------------------------------------------------------------------

class APIClientError(Exception):
    """Base for all API-client errors."""
    category: str = "unknown"


class NetworkError(APIClientError):
    """DNS / connection refused / no internet."""
    category = "network"


class TimeoutError(APIClientError):
    """Request timed out."""
    category = "timeout"


class AuthError(APIClientError):
    """401 Unauthorized -- bad or expired API key."""
    category = "auth"


class ServerError(APIClientError):
    """5xx after all retries exhausted."""
    category = "server"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class APIClient:
    """HTTP client for the Agent chat API with retry, timeout, and streaming."""

    MAX_RETRIES = 3
    TIMEOUT = 300

    def __init__(self, base_url: str, api_key: str, model: str = "deepseek-chat") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._last_error_message: str = ""   # human-readable, set on failure

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_message(
        self,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Send messages and return the full parsed JSON response."""
        payload = self._build_payload(messages)
        data = self._request_with_retry("POST", "/chat/completions", payload)
        return data

    def get_response(self, data: dict[str, Any]) -> str:
        """Extract the text response from an OpenAI-compatible API response."""
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return data.get("response", "")

    def stream_response(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Send messages and yield events via SSE streaming.

        Yields dicts:
          {"type": "text", "content": "token"}  -- normal text token
          {"type": "tool_calls", "calls": [...]}  -- accumulated tool calls at stream end
        """
        payload = self._build_payload(messages, tools=tools)
        payload["stream"] = True

        url = f"{self.base_url}/chat/completions"
        response = requests.post(
            url, headers=self._headers(), json=payload,
            timeout=self.TIMEOUT, stream=True,
        )
        response.raise_for_status()

        # Accumulate tool calls across chunks
        tool_calls_map: dict[int, dict[str, Any]] = {}

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                chunk = line[6:]
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                    choices = data.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})

                    # Normal text content
                    token = delta.get("content", "")
                    if token:
                        yield {"type": "text", "content": token}

                    # Tool calls in delta
                    tc_list = delta.get("tool_calls", [])
                    for tc in tc_list:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        entry = tool_calls_map[idx]
                        if "id" in tc and tc["id"]:
                            entry["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            entry["function"]["name"] = fn["name"]
                        if fn.get("arguments"):
                            entry["function"]["arguments"] += fn["arguments"]

                except json.JSONDecodeError:
                    continue

        # After [DONE], emit accumulated tool calls if any
        if tool_calls_map:
            calls = [tool_calls_map[i] for i in sorted(tool_calls_map)]
            yield {"type": "tool_calls", "calls": calls}

    def check_connection(self) -> bool:
        try:
            self.send_message(messages=[{"role": "user", "content": "ping"}])
            return True
        except Exception:
            return False

    @property
    def last_error_message(self) -> str:
        return self._last_error_message

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 384000,
        }
        if tools:
            payload["tools"] = tools
        return payload

    def _request_with_retry(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_auth_error = False

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = requests.request(
                    method, url, headers=self._headers(),
                    json=payload, timeout=self.TIMEOUT,
                )

                if response.status_code == 401:
                    body = response.text[:200]
                    msg = f"Authentication failed (401). Please check your API key in config.yaml. Response: {body}"
                    self._last_error_message = msg
                    raise AuthError(msg)

                if response.status_code < 500:
                    if response.status_code != 200:
                        body = response.text[:300]
                        msg = f"API error {response.status_code}: {body}"
                        self._last_error_message = msg
                        raise APIClientError(msg)
                    return response.json()

                # 5xx -- retry
                if attempt < self.MAX_RETRIES:
                    time.sleep(2 ** (attempt - 1))
                    continue

                body = response.text[:200] if hasattr(response, "text") else ""
                msg = f"Server error {response.status_code}: {body}"
                self._last_error_message = msg
                raise ServerError(msg)

            except ConnectionError:
                if attempt < self.MAX_RETRIES:
                    time.sleep(2 ** (attempt - 1))
                    continue
                msg = "Network error: cannot reach the server."
                self._last_error_message = msg
                raise NetworkError(msg)

            except ReadTimeout:
                if attempt < self.MAX_RETRIES:
                    time.sleep(1)
                    continue
                msg = "Request timed out. The server did not respond in time."
                self._last_error_message = msg
                raise TimeoutError(msg)

            except (AuthError, ServerError):
                raise  # don''t retry auth / final server errors

            except RequestException as exc:
                if attempt < self.MAX_RETRIES:
                    time.sleep(2 ** (attempt - 1))
                    continue
                msg = str(exc) or "Unknown request error."
                self._last_error_message = msg
                raise APIClientError(msg)

        msg = f"Request failed after {self.MAX_RETRIES} attempts"
        self._last_error_message = msg
        raise APIClientError(msg)
