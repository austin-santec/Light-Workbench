"""Bounded raw-TCP client for Santec engineering physical-port routing."""

import re
import socket
import time
from dataclasses import dataclass

from domain.extra_ports import PhysicalPortRouteResult, PhysicalPortRouteStatus


SANTEC_CLI_PORT = 2323
SANTEC_CLI_COMMAND_TEMPLATE = "writereg mems.ch %d"
SANTEC_CLI_LINE_TERMINATION = "\r\n"
SANTEC_CLI_CONNECT_TIMEOUT_SECONDS = 2.0
SANTEC_CLI_RESPONSE_TIMEOUT_SECONDS = 1.0
SANTEC_CLI_MAX_RESPONSE_BYTES = 4096
SANTEC_CLI_MAX_COMMAND_BYTES = 128


@dataclass(frozen=True)
class SantecCliProfile:
    """Named transport and response settings requiring hardware validation."""

    port: int = SANTEC_CLI_PORT
    command_template: str = SANTEC_CLI_COMMAND_TEMPLATE
    line_termination: str = SANTEC_CLI_LINE_TERMINATION
    connect_timeout_seconds: float = SANTEC_CLI_CONNECT_TIMEOUT_SECONDS
    response_timeout_seconds: float = SANTEC_CLI_RESPONSE_TIMEOUT_SECONDS
    max_response_bytes: int = SANTEC_CLI_MAX_RESPONSE_BYTES
    acknowledgement_pattern: str = r"(?:^|\s)(?:OK|SUCCESS|DONE)(?:\s|$)"
    error_pattern: str = r"(?:ERROR|INVALID|FAILED?|OUT\s+OF\s+RANGE|UNKNOWN)"
    readback_command_template: str | None = None
    readback_match_pattern: str | None = None
    framing: str = "raw"


class SantecCliRouter:
    """Send only the approved physical-port command to one known switch IP."""

    def __init__(self, profile=None, socket_factory=None, trace_callback=None):
        self.profile = profile or SantecCliProfile()
        self.socket_factory = socket_factory or socket.create_connection
        self.trace_callback = trace_callback

    def route(self, network_address: str, physical_port: int, maximum_port: int):
        profile = self.profile
        try:
            candidate = int(physical_port)
            ceiling = int(maximum_port)
        except (TypeError, ValueError) as error:
            raise ValueError("Physical port and safety ceiling must be integers.") from error
        if candidate < 1 or candidate > ceiling:
            raise ValueError(
                "Physical port %d is outside the permitted range 1-%d."
                % (candidate, ceiling)
            )
        if profile.framing != "raw":
            raise ValueError("Unsupported Santec CLI framing: %s" % profile.framing)

        command = profile.command_template % candidate
        payload = (command + profile.line_termination).encode("ascii", "strict")
        if len(payload) > profile.max_response_bytes or len(payload) > SANTEC_CLI_MAX_COMMAND_BYTES:
            raise ValueError("The generated Santec CLI command exceeds its bounded size.")

        started = time.perf_counter()
        self._trace(
            "switch_cli_connection_attempted",
            network_address=network_address,
            network_port=profile.port,
            physical_port=candidate,
            command_name="writereg mems.ch",
            status="attempted",
        )
        connection = None
        try:
            connection = self.socket_factory(
                (network_address, profile.port),
                profile.connect_timeout_seconds,
            )
            self._trace(
                "switch_cli_connection_completed",
                network_address=network_address,
                network_port=profile.port,
                physical_port=candidate,
                status="success",
            )
            connection.settimeout(profile.response_timeout_seconds)
            connection.sendall(payload)
            response, closed_without_response = self._read_bounded(connection)
            readback_response = b""
            if (
                profile.readback_command_template
                and not re.search(profile.error_pattern, response.decode("utf-8", "replace"), re.IGNORECASE)
            ):
                readback_command = profile.readback_command_template % candidate
                readback_payload = (
                    readback_command + profile.line_termination
                ).encode("ascii", "strict")
                if len(readback_payload) > SANTEC_CLI_MAX_COMMAND_BYTES:
                    raise ValueError("The configured CLI readback command is too long.")
                connection.sendall(readback_payload)
                readback_response, _unused = self._read_bounded(connection)
        except (TimeoutError, socket.timeout) as error:
            return self._failed(
                candidate,
                network_address,
                "TCP timeout while routing the physical port: %s" % error,
                started,
            )
        except (ConnectionError, OSError) as error:
            return self._failed(
                candidate,
                network_address,
                "Could not communicate with TCP port %d: %s" % (profile.port, error),
                started,
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass

        text = response.decode("utf-8", "replace").strip()
        readback_text = readback_response.decode("utf-8", "replace").strip()
        if text and re.search(profile.error_pattern, text, re.IGNORECASE):
            status = PhysicalPortRouteStatus.FAILED
            detail = "The switch engineering interface rejected the route command."
        elif profile.readback_command_template:
            pattern = (profile.readback_match_pattern or r"(?:^|\D)%d(?:\D|$)")
            try:
                pattern = pattern.format(port=candidate)
            except (IndexError, KeyError, ValueError):
                pass
            if "%d" in pattern:
                pattern = pattern % candidate
            if readback_text and re.search(pattern, readback_text):
                status = PhysicalPortRouteStatus.VERIFIED
                detail = "The configured engineering readback verified the route."
            else:
                status = PhysicalPortRouteStatus.UNVERIFIED
                detail = "The configured engineering readback did not verify the route."
        elif text and re.search(
            profile.acknowledgement_pattern, text, re.IGNORECASE
        ):
            status = PhysicalPortRouteStatus.ACKNOWLEDGED
            detail = "The switch acknowledged the route command."
        else:
            status = PhysicalPortRouteStatus.UNVERIFIED
            detail = (
                "The command was sent, but the response did not verify the route."
                if text
                else "The command was sent and the peer closed without a response."
            )
        result = PhysicalPortRouteResult(
            candidate,
            status,
            response=text,
            detail=detail,
            network_address=network_address,
            network_port=profile.port,
            readback_response=readback_text,
        )
        self._trace_result(result, started, closed_without_response)
        return result

    def _read_bounded(self, connection):
        chunks = []
        size = 0
        closed_without_response = False
        while size < self.profile.max_response_bytes:
            chunk = connection.recv(
                min(512, self.profile.max_response_bytes - size)
            )
            if not chunk:
                closed_without_response = size == 0
                break
            chunks.append(chunk)
            size += len(chunk)
            if b"\n" in chunk or b"\r" in chunk:
                break
            accumulated = b"".join(chunks).decode("utf-8", "replace")
            if re.search(
                self.profile.acknowledgement_pattern,
                accumulated,
                re.IGNORECASE,
            ) or re.search(
                self.profile.error_pattern,
                accumulated,
                re.IGNORECASE,
            ):
                break
        return b"".join(chunks), closed_without_response

    def _failed(self, candidate, network_address, detail, started):
        result = PhysicalPortRouteResult(
            candidate,
            PhysicalPortRouteStatus.FAILED,
            detail=detail,
            network_address=network_address,
            network_port=self.profile.port,
        )
        self._trace_result(result, started, False)
        return result

    def _trace_result(self, result, started, closed_without_response):
        self._trace(
            "switch_cli_route_completed",
            network_address=result.network_address,
            network_port=result.network_port,
            physical_port=result.physical_port,
            command_name="writereg mems.ch",
            verification_status=result.status.value,
            response=result.response,
            response_length=len(result.response),
            peer_closed_without_response=closed_without_response,
            details=result.detail,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            status=(
                "error"
                if result.status is PhysicalPortRouteStatus.FAILED
                else "success"
            ),
        )

    def _trace(self, event, **fields):
        if self.trace_callback is None:
            return
        try:
            self.trace_callback(event, **fields)
        except Exception:
            pass


__all__ = [
    "SANTEC_CLI_COMMAND_TEMPLATE",
    "SANTEC_CLI_CONNECT_TIMEOUT_SECONDS",
    "SANTEC_CLI_LINE_TERMINATION",
    "SANTEC_CLI_MAX_RESPONSE_BYTES",
    "SANTEC_CLI_PORT",
    "SANTEC_CLI_RESPONSE_TIMEOUT_SECONDS",
    "SantecCliProfile",
    "SantecCliRouter",
]
