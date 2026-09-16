"""Local-only relay for the Epic demo tester; it is deliberately not a general proxy."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
FORMATS = {"fhir", "fhir-xml", "hl7", "json", "ndjson"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upstream_origin(value: str, allow_loopback: bool = False) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Tunnel URL must be an HTTPS origin without a path, query, or credentials.")
    if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
        if not (allow_loopback and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
            raise ValueError("Use the HTTPS URL printed by devtunnel.")
    if not (parsed.hostname == "devtunnels.ms" or parsed.hostname.endswith(".devtunnels.ms")):
        if not (allow_loopback and parsed.hostname in {"127.0.0.1", "localhost"}):
            raise ValueError("Tunnel host must be under devtunnels.ms.")
    return f"{parsed.scheme}://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")


def fixed_path(kind: str, job_id: str = "", file_id: str = "", output_format: str = "fhir") -> str:
    if kind == "jobs":
        return "/v1/retrieval-jobs"
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("Invalid job identifier.")
    if kind == "status":
        return f"/v1/retrieval-jobs/{job_id}"
    if kind == "result" and output_format in FORMATS:
        return f"/v1/retrieval-jobs/{job_id}/result?format={output_format}"
    if kind == "file" and JOB_ID.fullmatch(file_id):
        return f"/v1/retrieval-jobs/{job_id}/files/{file_id}"
    raise ValueError("Invalid relay request.")


def request_upstream(origin: str, path: str, bearer: str, tunnel_token: str, body: bytes | None = None):
    headers = {"Authorization": f"******", "Accept": "*/*"}
    if tunnel_token:
        headers["X-Tunnel-Authorization"] = f"tunnel {tunnel_token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(origin + path, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with build_opener(NoRedirect).open(request, timeout=15) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("Upstream response exceeded the 2 MiB relay limit.")
            return response.status, dict(response.headers), data
    except HTTPError as exc:
        data = exc.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("Upstream response exceeded the 2 MiB relay limit.") from exc
        return exc.code, dict(exc.headers), data
    except URLError as exc:
        raise ValueError("Cannot reach the tunnel. Check tunnel login, connect token, and URL.") from exc


def make_handler(csrf: str, allow_loopback: bool):
    page = (Path(__file__).parent / "static" / "tester.html").read_bytes().replace(
        b"CSRF_TOKEN", csrf.encode()
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "EpicTester"

        def log_message(self, format, *args):
            pass

        def _same_origin(self):
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
                return False
            origin = self.headers.get("Origin")
            return not origin or origin in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}

        def _send(self, status, data, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._same_origin():
                self._send(403, b'{"error":"Forbidden origin."}')
            elif self.path == "/":
                self._send(200, page, "text/html; charset=utf-8")
            else:
                self._send(404, b'{"error":"Not found."}')

        def do_POST(self):
            if not self._same_origin() or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf):
                self._send(403, b'{"error":"Forbidden request."}')
                return
            if self.path not in {"/api/jobs", "/api/status", "/api/result", "/api/file"}:
                self._send(404, b'{"error":"Not found."}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 16384:
                    raise ValueError("Request is too large.")
                data = json.loads(self.rfile.read(length))
                origin = upstream_origin(data["tunnel_url"], allow_loopback)
                bearer, tunnel = data["bearer_token"], data.get("tunnel_token", "")
                if not isinstance(bearer, str) or not bearer or not isinstance(tunnel, str):
                    raise ValueError("API bearer token is required.")
                kind = self.path.rsplit("/", 1)[-1]
                payload = None
                if kind == "jobs":
                    payload = json.dumps(data["request"], separators=(",", ":")).encode()
                path = fixed_path(kind, data.get("job_id", ""), data.get("file_id", ""), data.get("format", "fhir"))
                status, headers, response = request_upstream(origin, path, bearer, tunnel, payload)
                if kind == "file" and 200 <= status < 300:
                    self.send_response(status)
                    self.send_header("Content-Type", headers.get("Content-Type", "application/octet-stream"))
                    self.send_header("Content-Disposition", headers.get("Content-Disposition", "attachment"))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(response)
                    return
                self._send(status, json.dumps({
                    "body": response.decode("utf-8", "replace"),
                    "headers": {k: headers.get(k, "") for k in ("X-Retrieval-Cache", "X-Collected-At", "X-Cache-Expires-At")},
                }).encode())
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode())

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Loopback-only Epic API tester.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(secrets.token_urlsafe(32), os.getenv("EPIC_TESTER_ALLOW_LOOPBACK") == "1"))
    print(f"Epic tester: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
