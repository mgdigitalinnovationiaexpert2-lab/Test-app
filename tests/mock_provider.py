"""Synthetic local OpenAI-compatible endpoint for real LiteLLM contract checks."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

counts = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if status == 429:
            self.send_header("Retry-After", "60")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send_json(200, counts)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        model = body["model"]
        counts[model] = counts.get(model, 0) + 1
        if model == "mock-error":
            self.send_json(500, {"error": {"message": "synthetic upstream failure", "type": "server_error"}})
        elif model == "mock-limit":
            self.send_json(429, {"error": {"message": "synthetic limit", "type": "rate_limit_error"}})
        else:
            self.send_json(200, {"id": "mock-only", "model": model, "object": "chat.completion",
                "created": 0, "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "synthetic-ok"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4}})


HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
