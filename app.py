"""Локальный HTTP-сервер без сторонних пакетов: python app.py."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import mimetypes
import socket
import sys

from model import evaluate, generate_example
from genetic import solve_genetic
from branch_bound import solve_branch_bound
from exhaustive import solve_exhaustive


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SOLVERS = {"genetic": solve_genetic, "branch_bound": solve_branch_bound,
           "exhaustive": solve_exhaustive}


class LocalServer(ThreadingHTTPServer):
    # В Windows SO_REUSEADDR может разрешить две копии сервера на одном порту.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/example":
            self.send_json(generate_example())
            return
        allowed = {"/": "index.html", "/style.css": "style.css",
                   "/app.js": "app.js", "/favicon.svg": "favicon.svg"}
        name = allowed.get(path)
        if name is None:
            self.send_error(404, "Not found")
            return
        file = STATIC / name
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(file.name)[0] or "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/api/evaluate", "/api/generate", "/api/solve"):
            self.send_error(404, "Not found")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 200_000:
                raise ValueError("Недопустимый размер запроса.")
            data = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Ожидается объект JSON.")
            if self.path == "/api/evaluate":
                result = evaluate(data)
            elif self.path == "/api/generate":
                result = generate_example(data.get("containerCount"), data.get("siteCount"), data.get("seed"))
            else:
                method = data.get("method")
                if not isinstance(method, str) or method not in SOLVERS:
                    raise ValueError("Неизвестный метод решения.")
                result = SOLVERS[method](data.get("task"), data.get("options"))
            self.send_json(result)
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    try:
        server = LocalServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise SystemExit(f"Не удалось открыть порт {port}: {exc}. Остановите прежний сервер или укажите другой порт.")
    print(f"Откройте http://127.0.0.1:{port}/ ; остановка: Ctrl+C", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        server.server_close()
