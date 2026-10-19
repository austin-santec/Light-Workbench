import socket
import unittest

from domain.extra_ports import PhysicalPortRouteStatus
from hardware.santec_cli import SantecCliProfile, SantecCliRouter


class FakeSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.timeout = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, payload):
        self.sent.append(payload)

    def recv(self, maximum):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response[:maximum]

    def close(self):
        self.closed = True


class SocketFactory:
    def __init__(self, connection=None, error=None):
        self.connection = connection
        self.error = error
        self.calls = []

    def __call__(self, address, timeout):
        self.calls.append((address, timeout))
        if self.error is not None:
            raise self.error
        return self.connection


class SantecCliRouterTests(unittest.TestCase):
    def route(self, responses, profile=None):
        connection = FakeSocket(responses)
        factory = SocketFactory(connection)
        result = SantecCliRouter(profile, factory).route("192.0.2.15", 49, 64)
        return result, connection, factory

    def test_exact_command_uses_port_2323_and_configured_termination(self):
        profile = SantecCliProfile(line_termination="\n")
        result, connection, factory = self.route([b"OK\n"], profile)

        self.assertEqual(factory.calls[0][0], ("192.0.2.15", 2323))
        self.assertEqual(connection.sent, [b"writereg mems.ch 49\n"])
        self.assertNotIn(b"[", connection.sent[0])
        self.assertEqual(result.status, PhysicalPortRouteStatus.ACKNOWLEDGED)
        self.assertTrue(connection.closed)

    def test_explicit_error_is_failed(self):
        result, _connection, _factory = self.route([b"ERROR invalid port\r\n"])
        self.assertEqual(result.status, PhysicalPortRouteStatus.FAILED)

    def test_recognized_acknowledgement_need_not_end_with_newline(self):
        result, _connection, _factory = self.route([b"OK"])
        self.assertEqual(result.status, PhysicalPortRouteStatus.ACKNOWLEDGED)

    def test_malformed_response_is_unverified(self):
        result, _connection, _factory = self.route([b"???\r\n"])
        self.assertEqual(result.status, PhysicalPortRouteStatus.UNVERIFIED)

    def test_peer_close_without_response_is_unverified(self):
        result, _connection, _factory = self.route([b""])
        self.assertEqual(result.status, PhysicalPortRouteStatus.UNVERIFIED)

    def test_response_timeout_blocks_route(self):
        result, _connection, _factory = self.route([socket.timeout("timed out")])
        self.assertEqual(result.status, PhysicalPortRouteStatus.FAILED)
        self.assertIn("timeout", result.detail.lower())

    def test_connection_refusal_blocks_route(self):
        factory = SocketFactory(error=ConnectionRefusedError("refused"))
        result = SantecCliRouter(socket_factory=factory).route("192.0.2.15", 49, 64)
        self.assertEqual(result.status, PhysicalPortRouteStatus.FAILED)
        self.assertIn("2323", result.detail)

    def test_configured_readback_can_verify_route(self):
        profile = SantecCliProfile(
            readback_command_template="readreg mems.ch %d",
            readback_match_pattern=r"^{port}$",
        )
        result, connection, _factory = self.route([b"OK\r\n", b"49\r\n"], profile)

        self.assertEqual(result.status, PhysicalPortRouteStatus.VERIFIED)
        self.assertEqual(
            connection.sent,
            [b"writereg mems.ch 49\r\n", b"readreg mems.ch 49\r\n"],
        )

    def test_port_above_safety_ceiling_is_rejected_before_connect(self):
        factory = SocketFactory(FakeSocket([b"OK\n"]))
        with self.assertRaises(ValueError):
            SantecCliRouter(socket_factory=factory).route("192.0.2.15", 65, 64)
        self.assertEqual(factory.calls, [])


if __name__ == "__main__":
    unittest.main()
