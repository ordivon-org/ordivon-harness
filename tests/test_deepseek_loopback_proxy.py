from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ordivon_harness.ordivon import deepseek


class _StreamResponse:
    status_code = 200

    def __init__(self, body: bytes = b"{}") -> None:
        self.body = body

    async def __aenter__(self) -> _StreamResponse:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def aiter_raw(self):
        yield self.body


class _AsyncClient:
    instances: list[_AsyncClient] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.request: tuple[str, str, dict[str, str], bytes] | None = None
        self.__class__.instances.append(self)

    async def __aenter__(self) -> _AsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        content: bytes,
    ) -> _StreamResponse:
        self.request = (method, url, headers, content)
        return _StreamResponse()


class DeepSeekLoopbackProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        _AsyncClient.instances.clear()

    def test_validated_proxy_accepts_only_plain_ipv4_loopback(self) -> None:
        self.assertIsNone(deepseek._validated_loopback_https_proxy(None))
        self.assertEqual(
            deepseek._validated_loopback_https_proxy("http://127.0.0.1:19081"),
            "http://127.0.0.1:19081",
        )
        for value in (
            "https://127.0.0.1:19081",
            "http://localhost:19081",
            "http://127.0.0.2:19081",
            "http://user:pass@127.0.0.1:19081",
            "http://127.0.0.1:19081/path",
            "http://192.168.0.1:19081",
            "http://example.com:19081",
        ):
            with self.assertRaises(ValueError, msg=value):
                deepseek._validated_loopback_https_proxy(value)

    def test_environment_proxy_must_be_unambiguous(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HTTPS_PROXY": "http://127.0.0.1:19081",
                "https_proxy": "http://127.0.0.1:19082",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                deepseek._loopback_https_proxy_from_environment()
        with patch.dict(
            os.environ,
            {
                "HTTPS_PROXY": "http://127.0.0.1:19081",
                "https_proxy": "http://127.0.0.1:19081",
            },
            clear=True,
        ):
            self.assertEqual(
                deepseek._loopback_https_proxy_from_environment(),
                "http://127.0.0.1:19081",
            )

    def test_httpx_handle_binds_only_validated_proxy_and_preserves_request(self) -> None:
        with patch.object(deepseek.httpx, "AsyncClient", _AsyncClient):
            handle = deepseek._HttpxPostHandle(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": "Bearer secret",
                    "Accept-Encoding": "gzip",
                },
                body=b"{}",
                timeout_seconds=3,
                max_response_bytes=1024,
                https_proxy="http://127.0.0.1:19081",
            )
            raw = handle.poll(2)
        self.assertEqual(raw, b"{}")
        self.assertEqual(len(_AsyncClient.instances), 1)
        client = _AsyncClient.instances[0]
        self.assertEqual(client.kwargs["proxy"], "http://127.0.0.1:19081")
        self.assertFalse(client.kwargs["trust_env"])
        self.assertFalse(client.kwargs["follow_redirects"])
        self.assertTrue(client.kwargs["http1"])
        self.assertFalse(client.kwargs["http2"])
        assert client.request is not None
        method, url, headers, body = client.request
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(headers["Accept-Encoding"], "identity")
        self.assertEqual(body, b"{}")

    def test_direct_httpx_path_has_no_proxy(self) -> None:
        with patch.object(deepseek.httpx, "AsyncClient", _AsyncClient):
            handle = deepseek._HttpxPostHandle(
                "https://api.deepseek.com/chat/completions",
                headers={},
                body=b"{}",
                timeout_seconds=3,
                max_response_bytes=1024,
            )
            raw = handle.poll(2)
        self.assertEqual(raw, b"{}")
        self.assertIsNone(_AsyncClient.instances[0].kwargs["proxy"])


if __name__ == "__main__":
    unittest.main()
