#!/usr/bin/env python3
import base64
import socket
import ssl

import os
AUTH = base64.b64encode(f"naiveuser:{os.environ['NAIVE_PASS']}".encode()).decode()
HOST = "alexklyvibe.ru"
PORT = 443

ctx = ssl.create_default_context()
raw = socket.create_connection(("127.0.0.1", PORT), timeout=20)
sock = ctx.wrap_socket(raw, server_hostname=HOST)
req = (
    f"CONNECT api.ipify.org:443 HTTP/1.1\r\n"
    f"Host: api.ipify.org:443\r\n"
    f"Proxy-Authorization: Basic {AUTH}\r\n"
    f"Proxy-Connection: Keep-Alive\r\n\r\n"
)
sock.sendall(req.encode())
resp = sock.recv(4096).decode(errors="replace")
status_line = resp.split("\r\n", 1)[0]
print("status:", status_line)
if " 200 " in status_line:
    print("CONNECT_OK")
    tun = ctx.wrap_socket(sock, server_hostname="api.ipify.org")
    tun.sendall(b"GET /?format=json HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
    body = tun.recv(4096).decode(errors="replace")
    print("ip_body:", body.split("\r\n\r\n", 1)[-1][:120])
else:
    print("CONNECT_FAIL")
    sock.close()
