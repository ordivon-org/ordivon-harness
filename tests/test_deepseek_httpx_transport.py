from __future__ import annotations

import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from ordivon_harness.ordivon.deepseek import HttpClientDeepSeekTransport
from ordivon_harness.ordivon.model import (
    AgentTurnAdapterError,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        pass

    @property
    def state(self) -> dict[str, object]:
        return self.server.state  # type: ignore[attr-defined, no-any-return]

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        requests = self.state["requests"]
        assert isinstance(requests, list)
        requests.append((self.path, body, self.headers.get("Accept-Encoding")))
        if self.path == "/pre":
            event = self.state["pre"]
            assert isinstance(event, threading.Event)
            event.set()
            time.sleep(1.5)
            self._write(200, b"late")
            return
        if self.path == "/body":
            self.send_response(200)
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(b"hello")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            event = self.state["body"]
            assert isinstance(event, threading.Event)
            event.set()
            time.sleep(1.5)
            try:
                self.wfile.write(b"-tail")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if self.path == "/redirect":
            self.send_response(307)
            self.send_header("Location", "/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        status = {
            "/408": 408,
            "/429": 429,
            "/500": 500,
            "/400": 400,
        }.get(self.path, 200)
        payload = b"x" * 64 if self.path == "/large" else b'{"ok":true}'
        self._write(status, payload)

    def _write(self, status: int, payload: bytes) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


class DeepSeekHttpxTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.daemon_threads = True
        cls.server.state = {}  # type: ignore[attr-defined]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.server.state = {  # type: ignore[attr-defined]
            "requests": [],
            "pre": threading.Event(),
            "body": threading.Event(),
        }
        self.transport = HttpClientDeepSeekTransport()

    @property
    def requests(self) -> list[tuple[str, bytes, str | None]]:
        return self.server.state["requests"]  # type: ignore[attr-defined, no-any-return]

    def _post(self, path: str, *, bound: int = 1024) -> bytes:
        return self.transport.post(
            self.base_url + path,
            headers={"Content-Type": "application/json"},
            body=b'{"exact":true}',
            timeout_seconds=1,
            max_response_bytes=bound,
        )

    def test_raw_request_identity_and_response_are_preserved(self) -> None:
        self.assertEqual(self._post("/ok"), b'{"ok":true}')
        self.assertEqual(
            self.requests,
            [("/ok", b'{"exact":true}', "identity")],
        )

    def test_status_mapping_is_single_request_and_provider_rejected(self) -> None:
        for path, expected in (
            ("/408", AgentTurnFailureCode.TIMEOUT),
            ("/429", AgentTurnFailureCode.UNAVAILABLE),
            ("/500", AgentTurnFailureCode.UNAVAILABLE),
            ("/400", AgentTurnFailureCode.REJECTED),
        ):
            before = len(self.requests)
            with self.assertRaises(AgentTurnAdapterError) as raised:
                self._post(path)
            self.assertEqual(raised.exception.failure_code, expected)
            self.assertEqual(
                raised.exception.dispatch_safety,
                AgentTurnDispatchSafety.PROVIDER_REJECTED,
            )
            self.assertEqual(len(self.requests), before + 1)

    def test_response_bound_and_redirect_policy_are_preserved(self) -> None:
        with self.assertRaisesRegex(
            AgentTurnAdapterError,
            "response exceeds the configured byte bound",
        ):
            self._post("/large", bound=16)
        with self.assertRaises(AgentTurnAdapterError) as raised:
            self._post("/redirect")
        self.assertEqual(raised.exception.failure_code, AgentTurnFailureCode.REJECTED)
        self.assertEqual([path for path, _, _ in self.requests].count("/ok"), 0)

    def test_pre_header_and_body_phase_cancellation_are_prompt(self) -> None:
        for path, event_name in (("/pre", "pre"), ("/body", "body")):
            handle = self.transport.start_post(
                self.base_url + path,
                headers={},
                body=b"{}",
                timeout_seconds=5,
                max_response_bytes=1024,
            )
            event = self.server.state[event_name]  # type: ignore[attr-defined]
            assert isinstance(event, threading.Event)
            self.assertTrue(event.wait(1))
            started = time.monotonic()
            handle.cancel()
            with self.assertRaises(AgentTurnAdapterError) as raised:
                handle.poll(1)
            self.assertEqual(
                raised.exception.failure_code,
                AgentTurnFailureCode.FAILED,
            )
            self.assertLess(time.monotonic() - started, 0.5)

    def test_timeout_maps_without_retry(self) -> None:
        handle = self.transport.start_post(
            self.base_url + "/pre",
            headers={},
            body=b"{}",
            timeout_seconds=0.05,
            max_response_bytes=1024,
        )
        with self.assertRaises(AgentTurnAdapterError) as raised:
            handle.poll(1)
        self.assertEqual(raised.exception.failure_code, AgentTurnFailureCode.TIMEOUT)
        self.assertEqual([path for path, _, _ in self.requests].count("/pre"), 1)

    def test_environment_proxy_is_not_inherited(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "http://127.0.0.1:1",
                "NO_PROXY": "",
            },
        ):
            self.assertEqual(self._post("/ok"), b'{"ok":true}')

    def test_invalid_url_and_non_https_proxy_target_fail_before_dispatch(self) -> None:
        invalid = self.transport.start_post(
            "not-a-url",
            headers={},
            body=b"{}",
            timeout_seconds=1,
            max_response_bytes=1024,
        )
        with self.assertRaisesRegex(ValueError, "absolute HTTP"):
            invalid.poll(1)
        proxied = HttpClientDeepSeekTransport(
            https_proxy="http://127.0.0.1:19081"
        ).start_post(
            self.base_url + "/ok",
            headers={},
            body=b"{}",
            timeout_seconds=1,
            max_response_bytes=1024,
        )
        with self.assertRaisesRegex(ValueError, "requires an HTTPS target"):
            proxied.poll(1)


if __name__ == "__main__":
    unittest.main()
