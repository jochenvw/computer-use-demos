"""Local-only relay for the Epic demo tester; it is deliberately not a general proxy."""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import secrets
import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
HEX32 = re.compile(r"^[0-9a-f]{32}$")
FORMATS = {"fhir", "fhir-xml", "hl7", "json", "ndjson", "omop"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upstream_origin(value: str, allow_loopback: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("Tunnel URL must be text.")
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Tunnel URL must be an HTTPS origin without a path, query, or credentials.")
    if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
        if not (allow_loopback and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
            raise ValueError("Use the HTTPS URL printed by devtunnel.")
    if not (parsed.hostname == "devtunnels.ms" or parsed.hostname.endswith(".devtunnels.ms")):
        if not (allow_loopback and parsed.hostname in {"127.0.0.1", "localhost"}):
            raise ValueError("Tunnel host must be under devtunnels.ms.")
    port = parsed.port
    return f"{parsed.scheme}://{parsed.hostname}" + (
        f":{port}" if port and not (parsed.scheme == "https" and port == 443) else ""
    )


def fixed_path(kind: str, job_id: str = "", file_id: str = "", output_format: str = "fhir") -> str:
    if not all(isinstance(value, str) for value in (kind, job_id, file_id, output_format)):
        raise ValueError("Path fields must be text.")
    if kind == "jobs":
        return "/v1/retrieval-jobs"
    if not HEX32.fullmatch(job_id):
        raise ValueError("Invalid job identifier.")
    if kind == "status":
        return f"/v1/retrieval-jobs/{job_id}"
    if kind == "transform":
        return f"/v1/retrieval-jobs/{job_id}/transform"
    if kind == "result":
        if output_format not in FORMATS:
            raise ValueError("Unsupported output format.")
        return f"/v1/retrieval-jobs/{job_id}/result?format={output_format}"
    if kind == "file" and HEX32.fullmatch(file_id):
        return f"/v1/retrieval-jobs/{job_id}/files/{file_id}"
    if kind == "file":
        raise ValueError("Invalid file identifier.")
    raise ValueError("Invalid relay request.")


def request_upstream(origin: str, path: str, bearer: str, tunnel_token: str, body: bytes | None = None, timeout: float = 15):
    headers = {"Authorization": " ".join(("Bearer", bearer)), "Accept": "*/*"}
    if tunnel_token:
        headers["X-Tunnel-Authorization"] = f"tunnel {tunnel_token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(origin + path, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with build_opener(NoRedirect).open(request, timeout=timeout) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("Upstream response exceeded the 2 MiB relay limit.")
            return response.status, dict(response.headers), data
    except HTTPError as exc:
        data = exc.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("Upstream response exceeded the 2 MiB relay limit.") from exc
        if 300 <= exc.code < 400:
            raise ValueError("Tunnel redirected the request. Check tunnel login or connect token.") from exc
        return exc.code, dict(exc.headers), data
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise ValueError("Cannot reach the tunnel. Check tunnel login, connect token, and URL.") from exc


def make_handler(
    csrf: str,
    allow_loopback: bool,
    configured_defaults: dict[str, str] | None = None,
):
    defaults = dict(configured_defaults or {})
    default_origin = defaults.get("tunnel_url", "")
    page = (Path(__file__).parent / "static" / "tester.html").read_bytes().replace(
        b"CSRF_TOKEN", csrf.encode()
    ).replace(
        b"TUNNEL_URL_DEFAULT", html.escape(default_origin, quote=True).encode()
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "EpicTester"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

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
            if self.path not in {"/api/jobs", "/api/status", "/api/result", "/api/file", "/api/transform"}:
                self._send(404, b'{"error":"Not found."}')
                return
            try:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError as exc:
                    raise ValueError("Invalid Content-Length header.") from exc
                if length < 0:
                    raise ValueError("Invalid Content-Length header.")
                if length == 0:
                    raise ValueError("Request body is required.")
                if length > 16384:
                    raise ValueError("Request is too large.")
                try:
                    data = json.loads(self.rfile.read(length))
                except json.JSONDecodeError as exc:
                    raise ValueError("Request body must be valid JSON.") from exc
                if not isinstance(data, dict):
                    raise ValueError("Request body must be a JSON object.")
                origin = upstream_origin(
                    data.get("tunnel_url") or defaults.get("tunnel_url", ""),
                    allow_loopback,
                )
                bearer = data.get("bearer_token") or defaults.get("bearer_token", "")
                tunnel = data.get("tunnel_token") or defaults.get("tunnel_token", "")
                if not isinstance(bearer, str) or not bearer:
                    raise ValueError("API bearer token is required.")
                if not isinstance(tunnel, str):
                    raise ValueError("Tunnel connect token must be text.")
                if "\r" in bearer or "\n" in bearer:
                    raise ValueError("API bearer token contains invalid characters.")
                if "\r" in tunnel or "\n" in tunnel:
                    raise ValueError("Tunnel connect token contains invalid characters.")
                kind = self.path.rsplit("/", 1)[-1]
                payload = None
                if kind == "jobs":
                    request_body = data.get("request")
                    if not isinstance(request_body, dict):
                        raise ValueError("Retrieval request must be a JSON object.")
                    payload = json.dumps(request_body, separators=(",", ":")).encode()
                elif kind == "transform":
                    schema = data.get("schema")
                    if not isinstance(schema, str) or not schema.strip():
                        raise ValueError("Paste a target schema or ontology first.")
                    payload = json.dumps({"schema": schema}).encode()
                path = fixed_path(kind, data.get("job_id", ""), data.get("file_id", ""), data.get("format", "fhir"))
                status, headers, response = request_upstream(
                    origin, path, bearer, tunnel, payload, 120 if kind == "transform" else 15,
                )
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
            except KeyError as exc:
                self._send(400, json.dumps({"error": f"Missing required field: {exc.args[0]}."}).encode())
            except TypeError:
                self._send(400, b'{"error":"Request fields have invalid types."}')
            except ValueError as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode())
            except (OSError, socket.timeout):
                self._send(408, b'{"error":"Request body timed out."}')

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Loopback-only Epic API tester.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the tester in the default browser.")
    args = parser.parse_args()
    defaults = {
        "tunnel_url": os.getenv("EPIC_TESTER_TUNNEL_URL", ""),
        "bearer_token": os.getenv("EPIC_TESTER_API_BEARER_TOKEN", ""),
        "tunnel_token": os.getenv("EPIC_TESTER_TUNNEL_TOKEN", ""),
    }
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(
            secrets.token_urlsafe(32),
            os.getenv("EPIC_TESTER_ALLOW_LOOPBACK") == "1",
            defaults,
        ),
    )
    address = f"http://127.0.0.1:{args.port}"
    print(f"Epic tester: {address}", flush=True)
    if defaults["tunnel_url"] and defaults["bearer_token"]:
        print("Using protected local demo connection; credential fields may remain blank.", flush=True)
    if args.open:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
