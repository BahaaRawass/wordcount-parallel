"""Tests for the classroom cluster task queue (lease expiry, duplicates, totals)."""

import threading

from wordcount.cluster import TaskQueue, run_worker, serve
from wordcount.core import count_lines, read_lines

SAMPLE = read_lines("data/sample.txt")


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def finish(queue, worker="w"):
    while (reply := queue.claim(worker))["task"]:
        t = reply["task"]
        queue.submit(worker, t["id"], count_lines(t["lines"], 0, len(t["lines"]), t["word"]))


def test_waits_until_started_then_counts_everything():
    q = TaskQueue(SAMPLE, "the", tasks=3)
    assert q.claim("a")["task"] is None and q.snapshot()["phase"] == "waiting"
    q.start()
    finish(q)
    s = q.snapshot()
    assert s["phase"] == "finished" and s["total_so_far"] == 7 == s["expected"]


def test_expired_lease_goes_back_to_queue_and_late_reply_is_ignored():
    clock = Clock()
    q = TaskQueue(SAMPLE, "the", tasks=3, lease=5, clock=clock)
    q.start()
    first = q.claim("crashy")["task"]          # crashy takes task 1 and goes silent
    clock.now = 6                               # lease is over
    again = q.claim("healthy")["task"]
    assert again["id"] == first["id"] and again["attempt"] == 2
    assert q.submit("healthy", again["id"], 2) == "accepted"
    assert q.submit("crashy", first["id"], 2) == "duplicate ignored"   # late reply
    finish(q, "healthy")
    s = q.snapshot()
    assert s["total_so_far"] == 7 and s["duplicates"] == 1
    assert s["tasks"][0]["expired"] == 1


def test_late_reply_that_arrives_first_is_accepted_once():
    clock = Clock()
    q = TaskQueue(SAMPLE, "the", tasks=2, lease=1, clock=clock)
    q.start()
    t = q.claim("slow")["task"]
    clock.now = 2
    q.claim("fast")                             # task re-leased to fast
    assert q.submit("slow", t["id"], 5) == "accepted"
    assert q.submit("fast", t["id"], 5) == "duplicate ignored"


def test_http_workers_end_to_end_with_a_crash():
    q = TaskQueue(SAMPLE, "the", tasks=6, lease=0.5)
    server = serve(q, host="127.0.0.1", port=0)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        q.start()
        crash = threading.Thread(target=run_worker, args=(url, "crashy"),
                                 kwargs={"crash_after": 1, "quiet": True})
        crash.start()
        crash.join(5)
        run_worker(url, "healthy", quiet=True)
        s = q.snapshot()
        assert s["phase"] == "finished" and s["total_so_far"] == 7
        assert sum(t["expired"] for t in s["tasks"]) == 1
    finally:
        server.shutdown()
        server.server_close()
