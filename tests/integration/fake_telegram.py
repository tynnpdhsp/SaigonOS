# SPDX-License-Identifier: Apache-2.0
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

TOKEN = sys.argv[1]
PORT = 8081
lock = Lock()
state = {"plan": [], "requests": [], "last_id": 0}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path != "/requests":
            self.reply(404, {"ok": False, "error_code": 404, "description": "Not Found"})
            return
        with lock:
            self.reply(200, state["requests"])

    def do_POST(self):
        content = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/plan":
            with lock:
                state["plan"], state["requests"] = json.loads(content), []
            self.reply(200, {"ok": True})
            return
        if self.path != f"/bot{TOKEN}/sendMessage":
            self.reply(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
            return
        with lock:
            step = state["plan"].pop(0) if state["plan"] else {}
            request = {"path": self.path, "body": json.loads(content), "at": time.time()}
            request["reply"] = None if step.get("drop") else step.get("status", 200)
            if request["reply"] == 200:
                state["last_id"] += 1
                request["message_id"] = state["last_id"]
            state["requests"].append(request)
        if step.get("drop"):
            self.close_connection = True
            return
        time.sleep(step.get("delay", 0))
        if request["reply"] == 200:
            message = {"message_id": request["message_id"], "date": int(request["at"])}
            self.reply(200, {"ok": True, "result": message})
            return
        error = {"ok": False, "error_code": request["reply"], "description": step["description"]}
        if "retry_after" in step:
            error["parameters"] = {"retry_after": step["retry_after"]}
        self.reply(request["reply"], error)

    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


ThreadingHTTPServer(("", PORT), Handler).serve_forever()
