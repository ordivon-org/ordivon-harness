from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ordivon_harness.ordivon import deepseek


class _Response:
    status = 200

    def read(self, _limit: int) -> bytes:
        return b'{}'

    def close(self) -> None:
        pass


class _Connection:
    instances: list['_Connection'] = []

    def __init__(self, host: str, *, port: int | None = None, timeout: float | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tunnel: tuple[str, int | None] | None = None
        self.request_args = None
        self.sock = None
        self.__class__.instances.append(self)

    def set_tunnel(self, host: str, port: int | None = None, headers=None) -> None:
        self.tunnel = (host, port)

    def request(self, method: str, path: str, *, body: bytes, headers: dict[str, str]) -> None:
        self.request_args = (method, path, body, headers)

    def getresponse(self) -> _Response:
        return _Response()

    def close(self) -> None:
        pass


class DeepSeekLoopbackProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        _Connection.instances.clear()

    def test_validated_proxy_accepts_only_plain_ipv4_loopback(self) -> None:
        self.assertIsNone(deepseek._validated_loopback_https_proxy(None))
        self.assertEqual(
            deepseek._validated_loopback_https_proxy('http://127.0.0.1:19081'),
            'http://127.0.0.1:19081',
        )
        for value in (
            'https://127.0.0.1:19081',
            'http://localhost:19081',
            'http://127.0.0.2:19081',
            'http://user:pass@127.0.0.1:19081',
            'http://127.0.0.1:19081/path',
            'http://192.168.0.1:19081',
            'http://example.com:19081',
        ):
            with self.assertRaises(ValueError, msg=value):
                deepseek._validated_loopback_https_proxy(value)

    def test_environment_proxy_must_be_unambiguous(self) -> None:
        with patch.dict(
            os.environ,
            {'HTTPS_PROXY': 'http://127.0.0.1:19081', 'https_proxy': 'http://127.0.0.1:19082'},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                deepseek._loopback_https_proxy_from_environment()
        with patch.dict(
            os.environ,
            {'HTTPS_PROXY': 'http://127.0.0.1:19081', 'https_proxy': 'http://127.0.0.1:19081'},
            clear=True,
        ):
            self.assertEqual(
                deepseek._loopback_https_proxy_from_environment(),
                'http://127.0.0.1:19081',
            )

    def test_http_client_handle_connects_to_proxy_and_tunnels_target(self) -> None:
        with patch.object(deepseek.http.client, 'HTTPSConnection', _Connection):
            handle = deepseek._HttpClientPostHandle(
                'https://api.deepseek.com/chat/completions',
                headers={'Authorization': 'Bearer secret'},
                body=b'{}',
                timeout_seconds=3,
                max_response_bytes=1024,
                https_proxy='http://127.0.0.1:19081',
            )
            raw = handle.poll(2)
        self.assertEqual(raw, b'{}')
        self.assertEqual(len(_Connection.instances), 1)
        connection = _Connection.instances[0]
        self.assertEqual((connection.host, connection.port), ('127.0.0.1', 19081))
        self.assertEqual(connection.tunnel, ('api.deepseek.com', 443))
        self.assertEqual(connection.request_args[0:2], ('POST', '/chat/completions'))
        self.assertEqual(connection.request_args[3]['Authorization'], 'Bearer secret')

    def test_direct_http_client_path_is_unchanged_without_proxy(self) -> None:
        with patch.object(deepseek.http.client, 'HTTPSConnection', _Connection):
            handle = deepseek._HttpClientPostHandle(
                'https://api.deepseek.com/chat/completions',
                headers={},
                body=b'{}',
                timeout_seconds=3,
                max_response_bytes=1024,
            )
            raw = handle.poll(2)
        self.assertEqual(raw, b'{}')
        connection = _Connection.instances[0]
        self.assertEqual((connection.host, connection.port), ('api.deepseek.com', None))
        self.assertIsNone(connection.tunnel)


if __name__ == '__main__':
    unittest.main()
