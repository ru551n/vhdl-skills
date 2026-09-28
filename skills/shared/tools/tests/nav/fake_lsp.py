"""Stand-in language server for LspSession tests.

Mode (argv[1]): echo | crash | hang | server_request | error. Every mode
answers ``initialize``; other requests get an echo of their method, params and
the notifications seen so far, unless the mode says otherwise.
"""

from __future__ import annotations

import json
import sys
import time


def read() -> dict:
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            sys.exit(0)
        if line in (b"\r\n", b"\n"):
            break
        name, _, value = line.decode().partition(":")
        if name.strip().lower() == "content-length":
            length = int(value)
    return json.loads(sys.stdin.buffer.read(length))


def send(message: dict) -> None:
    body = json.dumps(message).encode()
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    sys.stdout.buffer.flush()


mode = sys.argv[1]
notifications: list[str] = []
while True:
    message = read()
    if "id" not in message:
        notifications.append(message["method"])
        continue
    if message["method"] == "initialize":
        send({"jsonrpc": "2.0", "id": message["id"], "result": {"capabilities": {}}})
        continue
    if mode == "crash":
        sys.stderr.write("thread 'main' panicked at config.rs: boom\n")
        sys.stderr.flush()
        sys.exit(101)
    if mode == "hang":
        time.sleep(60)
    if mode == "error":
        send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "no such method"}})
        continue
    if mode == "server_request":
        send({"jsonrpc": "2.0", "id": 99, "method": "workspace/configuration", "params": {}})
        reply = read()
        if reply.get("id") != 99 or reply.get("result", "missing") is not None:
            sys.exit(3)
        send({"jsonrpc": "2.0", "method": "window/logMessage", "params": {"type": 3, "message": "hi"}})
    send(
        {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {"method": message["method"], "params": message["params"], "notifications": notifications},
        }
    )
