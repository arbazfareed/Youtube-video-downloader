from __future__ import annotations

import io
import socket
from urllib.parse import urlencode

import qrcode


def mobile_handoff_url(job_id: str, token: str, port: int) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.connect(("192.0.2.1", 80))
        host = connection.getsockname()[0]
    return f"http://{host}:{port}/mobile#{urlencode({'job': job_id, 'token': token})}"


def make_qr_png(url: str) -> bytes:
    image = qrcode.make(url)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
