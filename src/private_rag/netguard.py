"""Loopback-only socket guard: egress evidence you can re-run.

DEPLOYMENT.md claims no document, query, or embedding leaves the host.
This module makes that claim falsifiable in-process: while the guard is
active, every ``socket.connect`` in the Python process is intercepted
and any attempt to reach a non-loopback address raises ``EgressAttempt``
— the full ingest-and-query cycle runs under it in the test suite and in
``scripts/egress_check.py``, so a violation is a loud failure, not a
line to spot in a packet capture.

Scope, stated honestly: the guard sees this Python process. The Ollama
server is a separate localhost process whose egress it cannot observe —
an auditor covers that with an OS-level control (firewall rule on the
Ollama binary, or an air-gapped host), and DEPLOYMENT.md says so. DNS
resolution via the OS resolver is likewise outside ``connect`` and is
mooted by the same controls.
"""

from __future__ import annotations

import socket
from contextlib import contextmanager


class EgressAttempt(RuntimeError):
    pass


def _is_loopback(address) -> bool:
    if not isinstance(address, tuple) or not address:
        return False  # unix sockets etc. never leave the host, but be strict
    host = str(address[0])
    return (host in ("localhost", "::1")
            or host.startswith("127.")
            or host.startswith("::ffff:127."))


@contextmanager
def loopback_only():
    """Fail any non-loopback connection attempt while active."""
    real_connect = socket.socket.connect

    def guarded(self, address):
        if not _is_loopback(address):
            raise EgressAttempt(
                f"blocked non-loopback connection attempt to {address!r}")
        return real_connect(self, address)

    socket.socket.connect = guarded
    try:
        yield
    finally:
        socket.socket.connect = real_connect
