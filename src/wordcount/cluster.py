"""Classroom cluster: a fault-tolerant task queue that phones and laptops join over Wi-Fi.

The coordinator laptop runs a small web server. Anyone on the same network opens
the address in a browser (phone or laptop) and becomes a worker. Each worker
repeatedly asks for a task (a range of lines), counts the word in it, and sends
back its partial count. A live dashboard on the projector shows every task.

How failures are handled (the same idea as Amazon SQS or Celery):
  * A worker that takes a task holds a *lease* on it for a few seconds.
  * If the result does not arrive before the lease ends (tab closed, phone
    locked, Wi-Fi lost), the task goes back to the queue for another worker.
  * A task may therefore be *executed* more than once, but its result is
    *counted* only once: the first result for a task ID wins and any later
    result for the same task is reported as "duplicate ignored".

  uv run wordcount-cluster --file data/classroom.txt --word the
  uv run wordcount-cluster-worker --server http://192.168.1.20:8000 --name laptop-B
"""

import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

from wordcount.core import count_lines, partition_lines, read_lines, validate_word
from wordcount.cluster_pages import DASHBOARD_HTML, WORKER_HTML

DEFAULT_PORT = 8000


# ------------------------------------------------------------------ the queue
class TaskQueue:
    """All coordinator state. Every method takes the lock, so the web server's
    request threads never see a half-updated task (a critical section)."""

    def __init__(self, lines: list[str], word: str, tasks: int, lease: float = 5.0,
                 pace: float = 0.0, case_insensitive: bool = False, clock=time.monotonic):
        validate_word(word)
        self.lines, self.word, self.lease, self.pace = lines, word, lease, pace
        self.case_insensitive = case_insensitive
        self.task_count = max(1, min(tasks, len(lines) or 1))
        self.clock = clock
        self.lock = threading.Lock()
        self.expected = count_lines(lines, 0, len(lines), word, case_insensitive)
        self.workers: dict[str, dict] = {}
        self.reset()

    # -- lifecycle
    def reset(self) -> None:
        with getattr(self, "lock", threading.Lock()):
            self.tasks = [{"id": i + 1, "start": a, "stop": b, "state": "pending",
                           "worker": None, "lease_until": 0.0, "attempts": 0,
                           "partial": None, "done_by": None, "expired": 0}
                          for i, (a, b) in enumerate(partition_lines(len(self.lines),
                                                                     self.task_count))]
            self.phase = "waiting"          # waiting -> running -> finished
            self.started = self.finished = None
            self.events: deque = deque(maxlen=40)
            self.duplicates = 0
            for info in self.workers.values():
                info.update(done=0, current=None)
            self._event("Queue ready: %d tasks waiting for workers" % len(self.tasks))

    def start(self) -> None:
        with self.lock:
            if self.phase == "waiting":
                self.phase, self.started = "running", self.clock()
                self._event("START: workers may now take tasks")

    # -- helpers (call with the lock held)
    def _event(self, text: str) -> None:
        stamp = 0.0 if not getattr(self, "started", None) else self.clock() - self.started
        self.events.appendleft({"t": round(stamp, 2), "text": text})

    def _expire_leases(self) -> None:
        now = self.clock()
        for task in self.tasks:
            if task["state"] == "running" and now > task["lease_until"]:
                lost = task["worker"]
                task.update(state="pending", worker=None, expired=task["expired"] + 1)
                if lost in self.workers:
                    self.workers[lost]["seen"] = float("-inf")   # presumed dead until it calls again
                    if self.workers[lost]["current"] == task["id"]:
                        self.workers[lost]["current"] = None
                self._event(f"LEASE EXPIRED: no answer from {lost} for task {task['id']}; "
                            f"task {task['id']} goes back in the queue")

    # -- worker API
    def join(self, name: str) -> str:
        name = (name or "worker").strip()[:24] or "worker"
        with self.lock:
            unique, n = name, 2
            while unique in self.workers:
                unique, n = f"{name} ({n})", n + 1
            self.workers[unique] = {"done": 0, "current": None, "seen": self.clock()}
            self._event(f"JOIN: {unique}")
            return unique

    def claim(self, worker: str) -> dict:
        with self.lock:
            info = self.workers.setdefault(worker, {"done": 0, "current": None})
            info["seen"] = self.clock()
            if self.phase != "running":
                return {"task": None, "phase": self.phase}
            self._expire_leases()
            task = next((t for t in self.tasks if t["state"] == "pending"), None)
            if task is None:
                return {"task": None, "phase": self.phase}
            task["attempts"] += 1
            task.update(state="running", worker=worker,
                        lease_until=self.clock() + self.lease)
            info["current"] = task["id"]
            again = " (again)" if task["attempts"] > 1 else ""
            self._event(f"SEND  task {task['id']} (lines {task['start'] + 1}-{task['stop']})"
                        f" -> {worker}{again}")
            return {"phase": self.phase, "task": {
                "id": task["id"], "start": task["start"], "stop": task["stop"],
                "lines": self.lines[task["start"]:task["stop"]], "word": self.word,
                "case_insensitive": self.case_insensitive, "attempt": task["attempts"],
                "pace": self.pace}}

    def submit(self, worker: str, task_id: int, partial: int) -> str:
        with self.lock:
            if worker in self.workers:
                self.workers[worker]["seen"] = self.clock()
                if self.workers[worker]["current"] == task_id:
                    self.workers[worker]["current"] = None
            if not 1 <= task_id <= len(self.tasks):
                return "unknown task"
            task = self.tasks[task_id - 1]
            if task["state"] == "done":
                self.duplicates += 1
                self._event(f"DUPLICATE IGNORED: task {task_id} from {worker} "
                            f"(already counted from {task['done_by']})")
                return "duplicate ignored"
            late = task["worker"] not in (None, worker)
            task.update(state="done", partial=int(partial), done_by=worker, worker=None)
            if worker in self.workers:
                self.workers[worker]["done"] += 1
            self._event(f"RECV  task {task_id} partial={partial} from {worker}"
                        + ("  (late, but first result: accepted)" if late else ""))
            if all(t["state"] == "done" for t in self.tasks):
                self.phase, self.finished = "finished", self.clock()
                total = sum(t["partial"] for t in self.tasks)
                mark = "correct" if total == self.expected else "WRONG"
                self._event(f"FINISHED: total = {total} (expected {self.expected}, {mark})")
            return "accepted"

    # -- dashboard
    def snapshot(self) -> dict:
        with self.lock:
            if self.phase == "running":
                self._expire_leases()
            now = self.clock()
            done = [t for t in self.tasks if t["state"] == "done"]
            end = self.finished or now
            return {
                "phase": self.phase, "word": self.word, "expected": self.expected,
                "lines": len(self.lines), "lease": self.lease, "pace": self.pace,
                "total_so_far": sum(t["partial"] for t in done),
                "done": len(done), "tasks_total": len(self.tasks),
                "duplicates": self.duplicates,
                "elapsed": round(end - self.started, 1) if self.started else 0,
                "tasks": [{k: t[k] for k in ("id", "start", "stop", "state", "worker",
                                             "attempts", "partial", "done_by", "expired")}
                          | {"lease_left": round(max(0.0, t["lease_until"] - now), 1)
                             if t["state"] == "running" else None}
                          for t in self.tasks],
                "workers": [{"name": n, "done": w["done"], "current": w["current"],
                             "active": now - w.get("seen", now) < max(10.0, self.lease * 2)}
                            for n, w in self.workers.items()],
                "events": list(self.events)}


# ------------------------------------------------------------------ web server
def make_handler(queue: TaskQueue, phone_url: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the terminal readable
            pass

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: dict, code: int = 200) -> None:
            self._send(code, json.dumps(data).encode("utf-8"), "application/json")

        def _local(self) -> bool:
            return self.client_address[0] in ("127.0.0.1", "::1")

        def do_GET(self) -> None:
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if url.path in ("/", "/worker"):
                self._send(200, WORKER_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif url.path == "/dashboard":
                page = DASHBOARD_HTML.replace("{{PHONE_URL}}", phone_url)
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif url.path == "/api/state":
                self._json(queue.snapshot() | {"phone_url": phone_url,
                                               "can_control": self._local()})
            elif url.path == "/api/task":
                self._json(queue.claim(query.get("worker", ["?"])[0]))
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            if self.path == "/api/join":
                self._json({"name": queue.join(str(data.get("name", "")))})
            elif self.path == "/api/result":
                status = queue.submit(str(data.get("worker")), int(data.get("task_id", 0)),
                                      int(data.get("partial", 0)))
                self._json({"status": status})
            elif self.path in ("/api/start", "/api/reset"):
                if not self._local():
                    return self._json({"error": "only the coordinator laptop can do this"}, 403)
                queue.start() if self.path == "/api/start" else queue.reset()
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def lan_address() -> str:
    """The laptop's address on the Wi-Fi (no packet is actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def serve(queue: TaskQueue, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
          ready: threading.Event | None = None) -> ThreadingHTTPServer:
    phone_url = f"http://{lan_address()}:{port}"
    server = ThreadingHTTPServer((host, port), make_handler(queue, phone_url))
    server.daemon_threads = True
    if ready is not None:
        ready.set()
    return server


# ------------------------------------------------------------------ CLI worker
def _http(server: str, path: str, data: dict | None = None, timeout: float = 5.0) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # LAN: no proxy
    body = None if data is None else json.dumps(data).encode("utf-8")
    request = urllib.request.Request(server.rstrip("/") + path, data=body,
                                     headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run_worker(server: str, name: str, crash_after: int = 0, late: float = 0.0,
               stop: threading.Event | None = None, quiet: bool = False) -> int:
    """Pull tasks until the job is finished. Returns the number of tasks answered."""
    name = _http(server, "/api/join", {"name": name})["name"]
    say = (lambda *a: None) if quiet else (lambda text: print(f"[{name}] {text}", flush=True))
    say(f"joined {server}")
    taken = answered = 0
    while stop is None or not stop.is_set():
        reply = _http(server, "/api/task?worker=" + urllib.parse.quote(name))
        task = reply.get("task")
        if task is None:
            if reply.get("phase") == "finished":
                say("job finished")
                return answered
            time.sleep(0.3)
            continue
        taken += 1
        say(f"got task {task['id']} (lines {task['start'] + 1}-{task['stop']})")
        if crash_after and taken >= crash_after:
            say("SIMULATED CRASH: leaving without answering")
            return answered
        partial = count_lines(task["lines"], 0, len(task["lines"]), task["word"],
                              task["case_insensitive"])
        wait = task["pace"] + (late if late and taken == 1 else 0.0)
        if late and taken == 1:
            say(f"pretending to be slow: answering after {wait:.1f}s")
        time.sleep(wait)
        status = _http(server, "/api/result",
                       {"worker": name, "task_id": task["id"], "partial": partial})["status"]
        answered += 1
        say(f"task {task['id']} partial={partial}: {status}")
    return answered


def worker_main() -> None:
    parser = argparse.ArgumentParser(description="Join a classroom cluster from a terminal")
    parser.add_argument("--server", required=True, help="e.g. http://192.168.1.20:8000")
    parser.add_argument("--name", default=socket.gethostname())
    parser.add_argument("--crash-after", type=int, default=0,
                        help="demo: take the Nth task, then quit without answering")
    parser.add_argument("--late", type=float, default=0.0,
                        help="demo: answer the first task this many seconds late")
    args = parser.parse_args()
    try:
        run_worker(args.server, args.name, args.crash_after, args.late)
    except KeyboardInterrupt:
        print("stopped")
    except OSError as error:
        parser.exit(1, f"cannot reach {args.server}: {error}\n")


# ------------------------------------------------------------------ coordinator
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=Path("data/classroom.txt"))
    parser.add_argument("--word", default="the")
    parser.add_argument("--tasks", type=int, default=20)
    parser.add_argument("--lease", type=float, default=5.0,
                        help="seconds a worker may hold a task before it is given to another")
    parser.add_argument("--pace", type=float, default=1.5,
                        help="seconds each worker waits per task so the class can follow (0 = full speed)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--case-insensitive", action="store_true")
    parser.add_argument("--local", type=int, default=0,
                        help="also start N terminal workers on this laptop (to practise alone)")
    parser.add_argument("--crash-one", action="store_true",
                        help="with --local: one local worker quits in the middle of its 2nd task")
    parser.add_argument("--late-one", action="store_true",
                        help="with --local: one local worker answers its first task too late")
    parser.add_argument("--autostart", action="store_true",
                        help="start immediately instead of waiting for the Start button")
    args = parser.parse_args()
    try:
        queue = TaskQueue(read_lines(args.file), args.word, args.tasks, args.lease,
                          args.pace, args.case_insensitive)
        server = serve(queue, port=args.port)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    phone_url = f"http://{lan_address()}:{args.port}"
    print(f"Classroom cluster: {len(queue.lines)} lines, word={args.word!r}, "
          f"{len(queue.tasks)} tasks, lease={args.lease}s, expected total={queue.expected}")
    print(f"  Projector dashboard : http://localhost:{args.port}/dashboard")
    print(f"  Phones and laptops  : {phone_url}   (same Wi-Fi)")
    print("  Press Ctrl+C to stop.", flush=True)
    children = []
    for i in range(args.local):
        command = [sys.executable, "-m", "wordcount.cluster", "worker",
                   "--server", f"http://127.0.0.1:{args.port}", "--name", f"laptop-{i + 1}"]
        if args.crash_one and i == 0:
            command += ["--crash-after", "2"]
        if args.late_one and i == min(1, args.local - 1):
            command += ["--late", str(args.lease + 2)]
        children.append(subprocess.Popen(command))
    if args.autostart:
        queue.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        for child in children:
            child.terminate()
        server.server_close()


def entry() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        sys.argv.pop(1)
        worker_main()
    else:
        main()


if __name__ == "__main__":
    entry()
