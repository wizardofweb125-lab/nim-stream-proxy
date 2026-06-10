#!/usr/bin/env python3
"""Proxy NVIDIA NIM — force stream:true pour les gros modèles qui timeout en non-streaming.

Écoute sur 127.0.0.1:11436, forward vers integrate.api.nvidia.com.
Requête non-streaming → force stream côté NVIDIA → recollecte → répond d'un bloc.
"""

import http.server
import http.client
import json
import os
import ssl

PORT = int(os.environ.get("NIM_PROXY_PORT", "11436"))
NVIDIA_HOST = "integrate.api.nvidia.com"
API_KEY = os.environ.get("NVIDIA_API_KEY", "")


def _nvidia_request(method, path, body=None, stream=False):
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(NVIDIA_HOST, timeout=300, context=ctx)
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    conn.request(method, path, body=body, headers=headers)
    return conn.getresponse(), conn


class NimProxy(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            resp, conn = _nvidia_request("GET", self.path)
            data = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.getheader("Content-Type", "application/json"))
            self.end_headers()
            self.wfile.write(data)
            conn.close()
        except Exception as e:
            self._send_error(502, str(e))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""

        if self.path.endswith("/chat/completions") and raw:
            body = json.loads(raw)
            client_wants_stream = body.get("stream", False)
            if client_wants_stream:
                self._passthrough_stream(body)
            else:
                self._force_stream_and_collect(body)
        else:
            self._passthrough_post(raw)

    def _force_stream_and_collect(self, body):
        body["stream"] = True
        data = json.dumps(body).encode()
        try:
            resp, conn = _nvidia_request("POST", self.path, body=data)
            if resp.status != 200:
                err = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err)
                conn.close()
                return

            role = "assistant"
            content_parts = []
            reasoning_parts = []
            model = ""
            finish_reason = None
            usage = {}
            msg_id = ""

            while True:
                line = resp.readline()
                if not line:
                    break
                line = line.decode().strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                msg_id = chunk.get("id", msg_id)
                model = chunk.get("model", model)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for c in chunk.get("choices", []):
                    delta = c.get("delta", {})
                    if delta.get("role"):
                        role = delta["role"]
                    if delta.get("content"):
                        content_parts.append(delta["content"])
                    if delta.get("reasoning_content"):
                        reasoning_parts.append(delta["reasoning_content"])
                    if c.get("finish_reason"):
                        finish_reason = c["finish_reason"]

            conn.close()

            result = {
                "id": msg_id,
                "object": "chat.completion",
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": role, "content": "".join(content_parts)},
                    "finish_reason": finish_reason or "stop",
                }],
                "usage": usage,
            }
            out = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        except Exception as e:
            self._send_error(502, str(e))

    def _passthrough_stream(self, body):
        data = json.dumps(body).encode()
        try:
            resp, conn = _nvidia_request("POST", self.path, body=data)
            self.send_response(resp.status)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            while True:
                line = resp.readline()
                if not line:
                    break
                self.wfile.write(line)
                self.wfile.flush()
            conn.close()
        except Exception as e:
            self._send_error(502, str(e))

    def _passthrough_post(self, raw):
        try:
            resp, conn = _nvidia_request("POST", self.path, body=raw)
            data = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.getheader("Content-Type", "application/json"))
            self.end_headers()
            self.wfile.write(data)
            conn.close()
        except Exception as e:
            self._send_error(502, str(e))

    def _send_error(self, code, msg):
        err = json.dumps({"error": {"message": msg}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(err)

    def log_message(self, fmt, *args):
        print(f"[NIM] {args[0]}")


if __name__ == "__main__":
    if not API_KEY:
        print("ERREUR: NVIDIA_API_KEY non définie")
        exit(1)
    server = http.server.HTTPServer(("127.0.0.1", PORT), NimProxy)
    print(f"[NIM] Proxy sur http://127.0.0.1:{PORT} → {NVIDIA_HOST}")
    print(f"[NIM] Clé: ***{API_KEY[-4:]}")
    server.serve_forever()
