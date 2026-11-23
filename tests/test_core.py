import random
import re

import pytest

from wordcount.core import (count_lines, count_processes, count_threaded,
                            partition_lines, read_lines)
from wordcount.race import run_race


@pytest.mark.parametrize("workers", [1, 2, 3, 8])
@pytest.mark.parametrize("combine", ["lock", "slots"])
def test_hand_count_and_case(workers, combine):
    lines = read_lines("data/sample.txt")
    result = count_threaded(lines, "the", workers, combine, trace=True)
    assert result.total == 7
    assert sum(result.partials) == 7
    assert len(result.traces) == workers
    assert count_threaded(lines, "the", workers, combine, True).total == 9


@pytest.mark.parametrize("workers", [1, 2, 4, 20])
def test_boundaries_and_no_final_newline(workers):
    lines = ["the\n", "the the\n", "other there theme\n", "the"]
    assert count_threaded(lines, "the", workers).total == 4
    ranges = partition_lines(len(lines), workers)
    assert [i for start, stop in ranges for i in range(start, stop)] == list(range(len(lines)))


@pytest.mark.parametrize("combine", ["lock", "slots"])
def test_empty_file(tmp_path, combine):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    result = count_threaded(read_lines(path), "the", 8, combine, trace=True)
    assert result.total == 0
    assert len(result.traces) == 8
    assert all(t.start_line == t.stop_line for t in result.traces)


def test_whole_word_punctuation_and_underscore():
    lines = ["the other theme there another the_the the2 (the),the! the-the\n"]
    assert count_threaded(lines, "the", 4).total == 5


def test_unicode_casefold_and_crlf(tmp_path):
    path = tmp_path / "unicode.txt"
    path.write_bytes("café CAFÉ\r\nStraße STRASSE\r\n".encode("utf-8"))
    lines = read_lines(path)
    assert count_threaded(lines, "café", 3, case_insensitive=True).total == 2
    assert count_threaded(lines, "straße", 3, case_insensitive=True).total == 2


@pytest.mark.parametrize("word", ["", "two words", "the!", "a-b"])
def test_invalid_word(word):
    with pytest.raises(ValueError):
        count_threaded(["the\n"], word)


@pytest.mark.parametrize("workers", [0, -1])
def test_invalid_workers(workers):
    with pytest.raises(ValueError):
        count_threaded([], "the", workers)


def test_one_long_line_and_token():
    lines = ["x" * 100000 + " the " + "the" * 10000]
    assert count_threaded(lines, "the", 16).total == 1


def test_randomized_against_independent_regex_oracle():
    rng = random.Random(451)
    choices = ["the", "The", "other", "the_the", "there", "café", "7", "_"]
    separators = [" ", "\n", "-", ",", "\t", "!"]
    text = "".join(rng.choice(choices) + rng.choice(separators) for _ in range(1000))
    lines = text.splitlines(keepends=True)
    for insensitive in (False, True):
        tokens = re.findall(r"\w+", text)
        expected = sum((token.casefold() if insensitive else token) == "the" for token in tokens)
        for workers in (1, 3, 11):
            for combine in ("lock", "slots"):
                assert count_threaded(lines, "the", workers, combine, insensitive).total == expected


@pytest.mark.parametrize("workers", [1, 2, 8])
def test_processes_agree(workers):
    lines = read_lines("data/sample.txt")
    assert count_processes(lines, "the", workers).total == 7
    assert count_processes(lines, "the", workers, True).total == 9


def test_controlled_race():
    assert run_race(4, 20) == 20
    assert run_race(4, 20, locked=True) == 80


def test_worker_exception_reaches_caller(monkeypatch):
    def broken(*args):
        raise RuntimeError("intentional test failure")
    monkeypatch.setattr("wordcount.core.count_lines", broken)
    with pytest.raises(RuntimeError, match="intentional test failure"):
        count_threaded(["the"], "the", 2)


# ---------------------------------------------------------------- bonus tests
import socket as _socket
import threading as _threading

from wordcount.distributed import coordinate, serve_worker
from wordcount.natural_race import run_natural_race


def _free_port() -> int:
    with _socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_worker(name, **kwargs):
    port, ready, stop = _free_port(), _threading.Event(), _threading.Event()
    thread = _threading.Thread(target=serve_worker, daemon=True,
                               args=("127.0.0.1", port, name),
                               kwargs={"ready": ready, "stop": stop, "quiet": True, **kwargs})
    thread.start()
    assert ready.wait(5)
    return ("127.0.0.1", port), stop


SAMPLE = ["the cat and the dog.\n", "The other theme is there.\n", "the, THE; the!\n",
          "another the\n", "the\n", "end the."]


def test_distributed_matches_hand_count():
    a, stop_a = _start_worker("A")
    b, stop_b = _start_worker("B")
    try:
        result = coordinate(SAMPLE, "the", [a, b], tasks_count=3, verbose=False)
        assert result.total == 7
        assert sorted(result.partials) == [1, 2, 3]
        assert coordinate(SAMPLE, "the", [a, b], case_insensitive=True, verbose=False).total == 9
    finally:
        stop_a.set(); stop_b.set()


def test_distributed_recovers_from_crashed_worker():
    bad, stop_bad = _start_worker("crashy", crash_after=1)
    good, stop_good = _start_worker("good")
    try:
        result = coordinate(SAMPLE, "the", [bad, good], tasks_count=3, timeout=1.0, verbose=False)
        assert result.total == 7
        assert "127.0.0.1:%d" % bad[1] in result.dead_workers
    finally:
        stop_bad.set(); stop_good.set()


def test_distributed_recovers_from_unreachable_worker():
    good, stop_good = _start_worker("good")
    try:
        result = coordinate(SAMPLE, "the", [("127.0.0.1", _free_port()), good],
                            timeout=0.5, verbose=False)
        assert result.total == 7
        assert len(result.dead_workers) == 1
    finally:
        stop_good.set()


def test_natural_race_locked_is_exact():
    assert run_natural_race(4, 5000, locked=True) == 20000
