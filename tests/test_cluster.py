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


def make_docx(paragraphs: list[str]) -> bytes:
    import io
    import zipfile
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{p}</w:t></w:r></w:p>' for p in paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>')
    return buffer.getvalue()


def test_extract_lines_from_txt_and_docx():
    from wordcount.cluster import extract_lines
    import pytest
    assert extract_lines("a.txt", "﻿the cat\nthe end".encode("utf-8")) == ["the cat\n", "the end"]
    assert extract_lines("a.docx", make_docx(["the cat and the dog.", "THE end"])) == [
        "the cat and the dog.\n", "THE end\n"]
    with pytest.raises(ValueError):
        extract_lines("old.doc", b"binary")
    with pytest.raises(ValueError):
        extract_lines("broken.docx", b"not a zip")


def test_answer_from_an_old_job_is_ignored():
    q = TaskQueue(SAMPLE, "the", tasks=2)
    q.start()
    old = q.claim("phone")["task"]
    q.load(SAMPLE, "cat", tasks=2, source="new.txt")      # new job while phone is busy
    assert q.submit("phone", old["id"], 99, job=old["job"]) == "old job ignored"
    q.start()
    finish(q)
    s = q.snapshot()
    assert s["source"] == "new.txt" and s["total_so_far"] == s["expected"] == 1


def test_dashboard_can_load_a_word_file_over_http():
    import json
    import urllib.request
    q = TaskQueue(SAMPLE, "the", tasks=3)
    server = serve(q, host="127.0.0.1", port=0)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        request = urllib.request.Request(url + "/api/load?name=essay.docx&word=dog&tasks=2&ci=1",
                                         data=make_docx(["The dog.", "DOG and dogs", "a dog"]))
        reply = json.loads(opener.open(request).read())
        assert reply == {"ok": True, "lines": 3, "expected": 3}
        s = q.snapshot()
        assert s["source"] == "essay.docx" and s["word"] == "dog" and s["tasks_total"] == 2
        q.start()
        run_worker(url, "laptop", quiet=True)
        assert q.snapshot()["total_so_far"] == 3
    finally:
        server.shutdown()
        server.server_close()


def test_word_text_boxes_are_read_once():
    """A shape's text box sits inside a paragraph, and Word also saves a Fallback copy."""
    import io
    import zipfile
    from wordcount.cluster import extract_lines
    from wordcount.core import count_lines
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    box = '<w:txbxContent><w:p><w:r><w:t>the box</w:t></w:r></w:p></w:txbxContent>'
    xml = (f'<w:document xmlns:w="{w}" xmlns:mc="{mc}"><w:body>'
           f'<w:p><w:r><w:t>the outer </w:t></w:r><w:r><mc:AlternateContent>'
           f'<mc:Choice>{box}</mc:Choice><mc:Fallback>{box}</mc:Fallback>'
           f'</mc:AlternateContent></w:r></w:p></w:body></w:document>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", xml)
    lines = extract_lines("shapes.docx", buffer.getvalue())
    assert lines == ["the outer \n", "the box\n"]
    assert count_lines(lines, 0, len(lines), "the") == 2
