"""Line partitions, a Python token scanner, and two safe reductions."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import multiprocessing
import os
from pathlib import Path
import threading
from time import perf_counter


def is_word_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def validate_word(word: str) -> None:
    if not word or not all(is_word_character(c) for c in word):
        raise ValueError("word must contain only letters, digits, or underscores")


def read_lines(path: str | Path) -> list[str]:
    # Strict UTF-8 decoding makes malformed input an explicit error.
    with open(path, encoding="utf-8") as source:
        return source.readlines()


def partition_lines(line_count: int, workers: int) -> list[tuple[int, int]]:
    """Return exactly N adjacent, nonoverlapping half-open line ranges."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if line_count < 0:
        raise ValueError("line count must be nonnegative")
    return [(i * line_count // workers, (i + 1) * line_count // workers)
            for i in range(workers)]


def count_lines(lines: list[str], start: int, stop: int,
                word: str, case_insensitive: bool = False) -> int:
    """Count maximal Unicode alphanumeric/underscore tokens, using Python loops."""
    target = word.casefold() if case_insensitive else word
    count = 0
    for line_number in range(start, stop):
        line = lines[line_number]
        token_start = None
        for position, character in enumerate(line):
            if character.isalnum() or character == "_":
                if token_start is None:
                    token_start = position
            elif token_start is not None:
                token = line[token_start:position]
                if case_insensitive:
                    token = token.casefold()
                if token == target:
                    count += 1
                token_start = None
        # A final line need not end with a newline.
        if token_start is not None:
            token = line[token_start:]
            if case_insensitive:
                token = token.casefold()
            if token == target:
                count += 1
    return count


@dataclass
class ThreadTrace:
    name: str
    native_id: int
    start_line: int
    stop_line: int
    characters: int
    partial: int
    start_seconds: float
    end_seconds: float


@dataclass
class CountResult:
    total: int
    partials: list[int]
    traces: list[ThreadTrace]
    elapsed_seconds: float


def count_threaded(lines: list[str], word: str, workers: int = 1,
                   combine: str = "lock", case_insensitive: bool = False,
                   trace: bool = False) -> CountResult:
    validate_word(word)
    if combine not in ("lock", "slots"):
        raise ValueError("combine must be lock or slots")
    begin = perf_counter()
    ranges = partition_lines(len(lines), workers)
    partials = [0] * workers
    traces = [None] * workers
    errors = [None] * workers
    total = 0
    lock = threading.Lock()

    def worker(index: int, start: int, stop: int) -> None:
        nonlocal total
        try:
            started = perf_counter() - begin
            partial = count_lines(lines, start, stop, word, case_insensitive)
            partials[index] = partial  # Exactly one writer owns this slot.
            if combine == "lock":
                with lock:
                    total += partial  # One critical section per worker.
            if trace:
                traces[index] = ThreadTrace(
                    threading.current_thread().name, threading.get_native_id(),
                    start, stop, sum(len(lines[i]) for i in range(start, stop)),
                    partial, started, perf_counter() - begin)
        except BaseException as error:
            errors[index] = error

    threads = [threading.Thread(target=worker, args=(i, start, stop),
                                name=f"worker-{i + 1}")
               for i, (start, stop) in enumerate(ranges)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for error in errors:
        if error is not None:
            raise error
    if combine == "slots":
        total = sum(partials)  # Only after all writers have finished.
    return CountResult(total, partials, [t for t in traces if t is not None],
                       perf_counter() - begin)


def count_processes(lines: list[str], word: str, workers: int = 1,
                    case_insensitive: bool = False) -> CountResult:
    validate_word(word)
    ranges = partition_lines(len(lines), workers)
    if os.name == "nt" and workers > 61:
        raise ValueError("ProcessPoolExecutor on Windows supports at most 61 workers")
    begin = perf_counter()
    # Explicit spawn keeps the comparison consistent across operating systems.
    with ProcessPoolExecutor(max_workers=workers,
                             mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [pool.submit(count_lines, lines[start:stop], 0, stop - start,
                               word, case_insensitive) for start, stop in ranges]
        partials = [future.result() for future in futures]
    return CountResult(sum(partials), partials, [], perf_counter() - begin)
