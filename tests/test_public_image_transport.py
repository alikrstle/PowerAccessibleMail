from __future__ import annotations

import io
import socket
import ssl
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch

from accessible_mail.network_security import (
    UnsafeRemoteUrl, _PublicHTTPSConnection, _public_connection, public_http_opener, validate_public_http_url,
)


def address(ip="93.184.216.34", port=80):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


def fake_socket(data=b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc", ip="93.184.216.34", port=80):
    connection = Mock()
    connection.getpeername.return_value = (ip, port)
    connection.makefile.return_value = io.BytesIO(data)
    return connection


class PublicImageTransportTests(unittest.TestCase):
    def test_final_dns_answer_is_pinned_without_third_lookup(self):
        connection = fake_socket()
        with patch("accessible_mail.network_security.socket.getaddrinfo", side_effect=[
            [address()], [address()], [address("127.0.0.1")],
        ]) as dns, patch("accessible_mail.network_security.socket.socket", return_value=connection):
            with public_http_opener().open("http://images.example.com/picture", timeout=10) as response:
                self.assertEqual(response.read(4), b"abc")
            self.assertEqual(dns.call_count, 2)
        connection.connect.assert_called_once_with(("93.184.216.34", 80))

    def test_dns_rebinding_to_private_address_is_blocked_before_connection(self):
        with patch("accessible_mail.network_security.socket.getaddrinfo", side_effect=[
            [address()], [address("127.0.0.1")],
        ]), patch("accessible_mail.network_security.socket.socket") as create, self.assertRaises(UnsafeRemoteUrl):
            public_http_opener().open("http://images.example.com/image", timeout=10)
        create.assert_not_called()

    def test_mixed_public_and_private_answers_multicast_and_mapped_private_fail_closed(self):
        for answers in ([address(), address("10.0.0.1")], [address("224.0.0.1")],
                        [address("ff0e::1")], [address("::ffff:127.0.0.1")],
                        [address("169.254.169.254")], [address("100.64.0.1")]):
            with self.subTest(answers=answers), patch("accessible_mail.network_security.socket.getaddrinfo", return_value=answers), \
                    patch("accessible_mail.network_security.socket.socket") as create, self.assertRaises(UnsafeRemoteUrl):
                _public_connection(("example.com", 80), 10)
            create.assert_not_called()

    def test_peer_mismatch_closes_connection(self):
        connection = fake_socket(ip="127.0.0.1")
        with patch("accessible_mail.network_security.socket.getaddrinfo", return_value=[address()]), \
                patch("accessible_mail.network_security.socket.socket", return_value=connection), \
                self.assertRaises(UnsafeRemoteUrl):
            _public_connection(("example.com", 80), 10)
        connection.close.assert_called_once()

    def test_fallback_uses_only_addresses_from_validated_snapshot(self):
        first, second = fake_socket(), fake_socket(ip="8.8.8.8")
        first.connect.side_effect = TimeoutError()
        with patch("accessible_mail.network_security.socket.getaddrinfo", return_value=[address(), address("8.8.8.8")]) as dns, \
                patch("accessible_mail.network_security.socket.socket", side_effect=[first, second]):
            self.assertIs(_public_connection(("example.com", 80), 10), second)
        dns.assert_called_once()
        first.close.assert_called_once()
        second.connect.assert_called_once_with(("8.8.8.8", 80))

    def test_public_ipv6_numeric_connect(self):
        ip = "2606:4700:4700::1111"
        connection = fake_socket(ip=ip)
        with patch("accessible_mail.network_security.socket.getaddrinfo", return_value=[address(ip)]), \
                patch("accessible_mail.network_security.socket.socket", return_value=connection):
            self.assertIs(_public_connection(("example.com", 80), 10), connection)
        connection.connect.assert_called_once_with((ip, 80, 0, 0))

    def test_https_keeps_domain_for_sni_and_certificate_verification(self):
        connection = fake_socket(port=443)
        context = Mock()
        context.wrap_socket.return_value = connection
        with patch("accessible_mail.network_security.socket.getaddrinfo", return_value=[address(port=443)]), \
                patch("accessible_mail.network_security.socket.socket", return_value=connection):
            client = _PublicHTTPSConnection("images.example.com", context=context, timeout=10)
            client.connect()
            client.close()
        context.wrap_socket.assert_called_once_with(connection, server_hostname="images.example.com")

    def test_certificate_error_is_not_retried_insecurely(self):
        connection = fake_socket(port=443)
        context = Mock()
        context.wrap_socket.side_effect = ssl.SSLCertVerificationError("wrong hostname")
        with patch("accessible_mail.network_security.socket.getaddrinfo", return_value=[address(port=443)]), \
                patch("accessible_mail.network_security.socket.socket", return_value=connection), \
                patch("accessible_mail.network_security.trusted_https_context", return_value=context), \
                self.assertRaises(urllib.error.URLError):
            public_http_opener().open("https://images.example.com/image", timeout=10)
        context.wrap_socket.assert_called_once()
        connection.close.assert_called()

    def test_process_proxies_ignored_and_host_header_matches_original_url(self):
        connection = fake_socket()
        with patch("urllib.request.getproxies", return_value={"http": "http://127.0.0.1:8080"}) as proxies, \
                patch("accessible_mail.network_security.socket.getaddrinfo", return_value=[address()]), \
                patch("accessible_mail.network_security.socket.socket", return_value=connection):
            request = urllib.request.Request("http://images.example.com/image", headers={"Host": "internal.local"})
            with public_http_opener().open(request, timeout=10) as response:
                self.assertEqual(response.read(4), b"abc")
        proxies.assert_not_called()
        sent = b"".join(call.args[0] for call in connection.sendall.call_args_list)
        self.assertIn(b"Host: images.example.com", sent)
        self.assertNotIn(b"internal.local", sent)

    def test_redirect_to_private_address_is_blocked(self):
        connection = fake_socket(b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/image\r\nContent-Length: 0\r\n\r\n")

        def resolve(host, port, **_kwargs):
            return [address("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", port)]

        with patch("accessible_mail.network_security.socket.getaddrinfo", side_effect=resolve), \
                patch("accessible_mail.network_security.socket.socket", return_value=connection) as create, \
                self.assertRaises(urllib.error.HTTPError):
            public_http_opener().open("http://images.example.com/image", timeout=10)
        create.assert_called_once()

    def test_public_redirect_revalidates_and_pins_new_domain(self):
        first = fake_socket(b"HTTP/1.1 302 Found\r\nLocation: http://other.example.com/image\r\nContent-Length: 0\r\n\r\n")
        second = fake_socket(ip="8.8.8.8")

        def resolve(host, port, **_kwargs):
            return [address("8.8.8.8" if host == "other.example.com" else "93.184.216.34", port)]

        with patch("accessible_mail.network_security.socket.getaddrinfo", side_effect=resolve), \
                patch("accessible_mail.network_security.socket.socket", side_effect=[first, second]):
            with public_http_opener().open("http://images.example.com/image", timeout=10) as response:
                self.assertEqual(response.read(4), b"abc")
        second.connect.assert_called_once_with(("8.8.8.8", 80))

    def test_explicit_proxy_tunnel_and_non_http_urls_are_rejected(self):
        request = urllib.request.Request("https://images.example.com/image")
        request.set_proxy("proxy.example.com:8080", "http")
        with self.assertRaises(UnsafeRemoteUrl):
            public_http_opener().open(request, timeout=10)
        for url in ("file:///C:/secret", "http://a.local/image", "http://localhost/image",
                    "http://user:pass@example.com/image", "http://example.com:0/image"):
            with self.subTest(url=url), self.assertRaises(UnsafeRemoteUrl):
                validate_public_http_url(url)


if __name__ == "__main__":
    unittest.main()
