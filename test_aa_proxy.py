import unittest
from unittest.mock import patch
import socket
from aa_proxy import _is_private_host

class TestIsPrivateHost(unittest.TestCase):
    def _mock_infos(self, *ips):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0)) for ip in ips]

    @patch('socket.getaddrinfo')
    def test_public_ips(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = self._mock_infos('8.8.8.8')
        self.assertFalse(_is_private_host('google.com'))

        mock_getaddrinfo.return_value = self._mock_infos('1.1.1.1', '142.250.190.46')
        self.assertFalse(_is_private_host('cloudflare-dns.com'))

        # IPv6 public
        mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2607:f8b0:4005:80b::200e', 0))]
        self.assertFalse(_is_private_host('ipv6.google.com'))

    @patch('socket.getaddrinfo')
    def test_private_ipv4(self, mock_getaddrinfo):
        # Test each private/unsafe IPv4 range
        test_cases = [
            '10.0.0.1',        # 10.0.0.0/8
            '127.0.0.1',       # 127.0.0.0/8
            '172.16.0.1',      # 172.16.0.0/12
            '172.31.255.255',  # 172.16.0.0/12 upper bound
            '192.168.1.1',     # 192.168.0.0/16
            '169.254.169.254', # 169.254.0.0/16 link-local
            '0.0.0.0',         # 0.0.0.0/8
            '100.64.0.1',      # 100.64.0.0/10 CGN
            '100.127.255.255', # 100.64.0.0/10 CGN upper bound
            '198.18.0.1',      # 198.18/15 benchmark
            '198.19.255.255',  # 198.18/15 benchmark
            '224.0.0.1',       # multicast
            '240.0.0.1',       # reserved
            '255.255.255.255', # broadcast
        ]

        for ip in test_cases:
            with self.subTest(ip=ip):
                mock_getaddrinfo.return_value = self._mock_infos(ip)
                self.assertTrue(_is_private_host('test.local'))

    @patch('socket.getaddrinfo')
    def test_private_ipv6(self, mock_getaddrinfo):
        # Test private/unsafe IPv6 ranges
        test_cases = [
            '::1',              # loopback
            '::ffff:127.0.0.1', # IPv4-mapped loopback
            'fe80::1',          # link-local
            'fc00::1',          # unique local
            'fd00::1',          # unique local
            '169.254::1',       # IPv4-mapped link-local
        ]

        for ip in test_cases:
            with self.subTest(ip=ip):
                mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', (ip, 0))]
                self.assertTrue(_is_private_host('test.local'))

    @patch('socket.getaddrinfo')
    def test_mixed_ips_one_private(self, mock_getaddrinfo):
        # If one IP is private, it should be blocked
        mock_getaddrinfo.return_value = self._mock_infos('8.8.8.8', '127.0.0.1')
        self.assertTrue(_is_private_host('mixed.local'))

    @patch('socket.getaddrinfo')
    def test_dns_failure(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
        self.assertTrue(_is_private_host('nonexistent.domain'))

    @patch('socket.getaddrinfo')
    def test_malformed_ip(self, mock_getaddrinfo):
        # Test a malformed IPv4 address string (e.g. invalid integer parts)
        mock_getaddrinfo.return_value = self._mock_infos('10.a.b.c')
        self.assertTrue(_is_private_host('malformed.local'))

if __name__ == '__main__':
    unittest.main()
