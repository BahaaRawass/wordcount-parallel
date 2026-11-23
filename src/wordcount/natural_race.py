"""Bonus: a natural lost-update race, with no barriers and no sleeps.

With the GIL on, plain `counter += 1` from several threads usually happens to
give the right answer. On free-threaded Python (GIL off) the threads really
run at the same time and many updates are lost unless the lock is used.

  uv run wordcount-natural-race
  uv run --python 3.13t wordcount-natural-race
"""

import argparse
import sys
import threading


def run_natural_race(workers: int = 4, increments: int = 200_000,
                     locked: bool = False) -> int:
    counter = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal counter
        for _ in range(increments):
            if locked:
                with lock:
                    counter += 1
            else:
                counter += 1  # read, add, write: three steps that can interleave

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return counter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--increments", type=int, default=200_000)
    args = parser.parse_args()
    gil = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
    expected = args.threads * args.increments
    unsafe = run_natural_race(args.threads, args.increments)
    safe = run_natural_race(args.threads, args.increments, locked=True)
    print(f"NATURAL RACE (no barriers, no sleeps), GIL {'ON' if gil else 'OFF'}")
    print(f"Expected={expected} unsafe={unsafe} lost={expected - unsafe} locked={safe}")


if __name__ == "__main__":
    main()
