"""Distributed word count over TCP sockets: one coordinator, several workers.

Each worker is a separate process (on this laptop or on another laptop on the
same network). The coordinator splits the file into line-range tasks, sends
each task as one JSON message, and adds the partial counts that come back.

If a worker does not answer within the timeout (crashed, Wi-Fi turned off,
script closed), the coordinator marks it dead and gives its task to another
worker. Each task ID is accepted only once, so a late duplicate reply can
never be counted twice.

Message format (one JSON object per line, UTF-8):
  coordinator -> worker  {"task_id": 2, "start": 2, "stop": 4,
                          "word": "the", "case_insensitive": false,
                          "lines": ["the, THE; the!\\n", "another the\\n"]}
  worker -> coordinator  {"task_id": 2, "partial": 3, "worker": "laptop-B"}
"""

import argparse
from dataclasses import dataclass, field
import json
import queue
import socket
import socketserver
import subprocess
import sys
import threading
import time

from wordcount.core import count_lines, partition_lines, read_lines, validate_word

DEFAULT_PORT = 5151


# ----------------------------------------------------------------- worker side
def handle_task(message: dict) -> int:
    lines = message["lines"]
    return count_lines(lines, 0, len(lines), message["word"],
                       message.get("case_insensitive", False))


def serve_worker(host: str, port: int, name: str, crash_after: int = 0,
                 delay: float = 0.0, ready: threading.Event | None = None,
                 stop: threading.Event | None = None, quiet: bool = False) -> None:
    """Run a worker until stopped. crash_after=N exits instead of answering task N."""
    handled = {"n": 0}
    lock = threading.Lock()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            raw = self.rfile.readline().strip()
            if not raw:  # connection probe or empty line
                return
            message = json.loads(raw.decode("utf-8"))
            with lock:
                handled["n"] += 1
                number = handled["n"]
            if not quiet:
                print(f"[{name}] received task {message['task_id']}: "
                      f"lines {message['start'] + 1}-{message['stop']} "
                      f"({len(message['lines'])} lines)", flush=True)
            if crash_after and number >= crash_after:
                if not quiet:
                    print(f"[{name}] SIMULATED CRASH: exiting without replying", flush=True)
                self.connection.close()
                if stop is not None:
                    stop.set()
                    return
                import os
                os._exit(1)
            if delay:
                time.sleep(delay)
            partial = handle_task(message)
            reply = {"task_id": message["task_id"], "partial": partial, "worker": name}
            self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))
            if not quiet:
                print(f"[{name}] sent back task {message['task_id']}: partial={partial}",
                      flush=True)

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((host, port), Handler) as server:
        server.timeout = 0.2
        if not quiet:
            print(f"[{name}] listening on {host}:{port}", flush=True)
        if ready is not None:
            ready.set()
        while stop is None or not stop.is_set():
            server.handle_request()


# ------------------------------------------------------------ coordinator side
@dataclass
class Task:
    task_id: int
    start: int
    stop: int


@dataclass
class DistributedResult:
    total: int
    partials: dict = field(default_factory=dict)      # task_id -> partial
    owners: dict = field(default_factory=dict)        # task_id -> worker name
    log: list = field(default_factory=list)           # human-readable message trace
    dead_workers: list = field(default_factory=list)
    elapsed_seconds: float = 0.0


def send_task(address: tuple[str, int], task: Task, lines: list[str], word: str,
              case_insensitive: bool, timeout: float) -> dict:
    message = {"task_id": task.task_id, "start": task.start, "stop": task.stop,
               "word": word, "case_insensitive": case_insensitive,
               "lines": lines[task.start:task.stop]}
    with socket.create_connection(address, timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall((json.dumps(message) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = connection.recv(65536)
            if not chunk:
                raise ConnectionError("worker closed the connection without a reply")
            data += chunk
    return json.loads(data.decode("utf-8"))


def coordinate(lines: list[str], word: str, workers: list[tuple[str, int]],
               tasks_count: int | None = None, case_insensitive: bool = False,
               timeout: float = 3.0, verbose: bool = True) -> DistributedResult:
    validate_word(word)
    if not workers:
        raise ValueError("at least one worker address is required")
    begin = time.perf_counter()
    count = tasks_count or len(workers)
    tasks = [Task(i + 1, start, stop)
             for i, (start, stop) in enumerate(partition_lines(len(lines), count))]
    pending: queue.Queue[Task] = queue.Queue()
    for task in tasks:
        pending.put(task)
    result = DistributedResult(total=0)
    lock = threading.Lock()
    alive = {f"{h}:{p}" for h, p in workers}

    def say(text: str) -> None:
        with lock:
            stamp = time.perf_counter() - begin
            result.log.append(f"{stamp:6.3f}s  {text}")
            if verbose:
                print(f"{stamp:6.3f}s  {text}", flush=True)

    def all_done() -> bool:
        with lock:
            return len(result.partials) == len(tasks)

    def dispatcher(address: tuple[str, int]) -> None:
        name = f"{address[0]}:{address[1]}"
        while not all_done():
            try:
                task = pending.get(timeout=0.05)
            except queue.Empty:
                continue
            say(f"SEND  task {task.task_id} (lines {task.start + 1}-{task.stop}) -> {name}")
            try:
                reply = send_task(address, task, lines, word, case_insensitive, timeout)
            except (OSError, ConnectionError, ValueError) as error:
                say(f"FAIL  {name} on task {task.task_id}: {type(error).__name__}; "
                    f"worker marked dead, task {task.task_id} goes back in the queue")
                with lock:
                    alive.discard(name)
                    result.dead_workers.append(name)
                pending.put(task)
                return
            with lock:
                duplicate = reply["task_id"] in result.partials
                if not duplicate:
                    result.partials[reply["task_id"]] = reply["partial"]
                    result.owners[reply["task_id"]] = reply.get("worker", name)
            say(f"RECV  task {reply['task_id']} partial={reply['partial']} "
                f"from {reply.get('worker', name)}"
                + ("  (duplicate ignored)" if duplicate else ""))

    threads = [threading.Thread(target=dispatcher, args=(address,), daemon=True)
               for address in workers]
    for thread in threads:
        thread.start()
    while not all_done():
        with lock:
            nobody_left = not alive
        if nobody_left:
            raise RuntimeError("every worker failed; tasks could not be completed")
        time.sleep(0.02)
    for thread in threads:
        thread.join(timeout=timeout + 1)
    result.total = sum(result.partials.values())
    result.elapsed_seconds = time.perf_counter() - begin
    return result


# ------------------------------------------------------------------- commands
def parse_address(text: str) -> tuple[str, int]:
    host, _, port = text.rpartition(":")
    if not host:
        return text, DEFAULT_PORT
    return host, int(port)


def worker_main() -> None:
    parser = argparse.ArgumentParser(description="Run one word-count worker")
    parser.add_argument("--host", default="0.0.0.0",
                        help="0.0.0.0 accepts connections from other laptops")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--name", default=socket.gethostname())
    parser.add_argument("--crash-after", type=int, default=0,
                        help="demo only: exit instead of answering the Nth task")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="demo only: seconds to wait before answering")
    args = parser.parse_args()
    try:
        serve_worker(args.host, args.port, args.name, args.crash_after, args.delay)
    except KeyboardInterrupt:
        print(f"[{args.name}] stopped")


def coordinator_main() -> None:
    parser = argparse.ArgumentParser(description="Send line ranges to workers and add results")
    parser.add_argument("--file", required=True)
    parser.add_argument("--word", required=True)
    parser.add_argument("--workers", nargs="*", default=[],
                        help="worker addresses, e.g. 192.168.43.12:5151 192.168.43.15:5151")
    parser.add_argument("--local", type=int, default=0,
                        help="start N worker processes on this laptop (simulated cluster)")
    parser.add_argument("--crash-one", action="store_true",
                        help="with --local: the first local worker crashes on its first task")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="with --local: each worker waits this long, so the audience can follow")
    parser.add_argument("--show-workers", action="store_true",
                        help="with --local: also print the workers' own messages")
    parser.add_argument("--tasks", type=int, default=0,
                        help="number of line-range tasks (default: one per worker)")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--case-insensitive", action="store_true")
    args = parser.parse_args()

    addresses = [parse_address(text) for text in args.workers]
    children = []
    try:
        for i in range(args.local):
            port = DEFAULT_PORT + 10 + i
            command = [sys.executable, "-m", "wordcount.distributed", "worker",
                       "--host", "127.0.0.1", "--port", str(port), "--name", f"worker-{i + 1}"]
            if args.crash_one and i == 0:
                command += ["--crash-after", "1"]
            if args.delay:
                command += ["--delay", str(args.delay)]
            output = None if args.show_workers else subprocess.DEVNULL
            children.append(subprocess.Popen(command, stdout=output))
            addresses.append(("127.0.0.1", port))
        if children:
            wait_for_ports(addresses[-len(children):])
        lines = read_lines(args.file)
        print(f"Coordinator: {len(lines)} lines, word={args.word!r}, "
              f"{len(addresses)} workers, timeout={args.timeout}s", flush=True)
        result = coordinate(lines, args.word, addresses, args.tasks or None,
                            args.case_insensitive, args.timeout)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    finally:
        for child in children:
            child.terminate()
    order = sorted(result.partials)
    print("Reduction: " + " + ".join(str(result.partials[t]) for t in order)
          + f" = {result.total}")
    if result.dead_workers:
        print("Recovered from failed workers: " + ", ".join(result.dead_workers))
    print(f"TOTAL={result.total}")
    print(f"Elapsed={result.elapsed_seconds:.3f}s")


def wait_for_ports(addresses: list[tuple[str, int]], limit: float = 10.0) -> None:
    deadline = time.time() + limit
    for host, port in addresses:
        while True:
            try:
                with socket.create_connection((host, port), timeout=0.2) as probe:
                    probe.sendall(b"\n")  # an empty line is ignored by the worker
                break
            except OSError:
                if time.time() > deadline:
                    raise OSError(f"worker {host}:{port} did not start")
                time.sleep(0.1)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        sys.argv.pop(1)
        worker_main()
    else:
        if len(sys.argv) > 1 and sys.argv[1] == "coordinator":
            sys.argv.pop(1)
        coordinator_main()


if __name__ == "__main__":
    main()
