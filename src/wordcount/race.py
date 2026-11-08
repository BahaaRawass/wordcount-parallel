"""Deliberately enforce a lost-update interleaving; never used for counting."""

import argparse
import threading
import time


def run_race(workers: int = 4, iterations: int = 100, locked: bool = False) -> int:
    if workers < 2 or iterations < 1:
        raise ValueError("use at least two workers and one iteration")
    counter = 0
    barrier = threading.Barrier(workers)
    lock = threading.Lock()

    def worker() -> None:
        nonlocal counter
        for _ in range(iterations):
            if locked:
                with lock:
                    previous = counter
                    time.sleep(0)  # A yield cannot expose a half-finished update.
                    counter = previous + 1
            else:
                previous = counter
                barrier.wait()  # Every worker has read the same old value.
                time.sleep(0)
                counter = previous + 1
                barrier.wait()  # All writes finish before the next round.

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return counter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    try:
        unsafe = run_race(args.threads, args.iterations)
        safe = run_race(args.threads, args.iterations, locked=True)
    except ValueError as error:
        parser.error(str(error))
    expected = args.threads * args.iterations
    print("CONTROLLED RACE DEMO: barriers enforce stale reads; sleep(0) yields.")
    print("This is not a claim that ordinary += fails on every CPython run.")
    print(f"Expected={expected} unsafe={unsafe} lost={expected - unsafe} locked={safe}")


if __name__ == "__main__":
    main()
