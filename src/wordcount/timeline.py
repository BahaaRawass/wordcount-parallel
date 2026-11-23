"""Bonus visual: a timeline (Gantt chart) of when each thread is really working.

Each worker processes its line range in small blocks and records the start and
end time of every block. With the GIL on, the blocks of different threads take
turns; with the GIL off, they overlap in time.

  uv run wordcount-timeline --file data/large.txt --threads 4 --output results/timeline-gil-on.json
  uv run --python 3.13t wordcount-timeline --file data/large.txt --threads 4 --output results/timeline-gil-off.json
  uv run wordcount-timeline --plot results/timeline-gil-on.json results/timeline-gil-off.json --output results/timeline.png
"""

import argparse
import json
from pathlib import Path
import sys
import threading
from time import perf_counter

from wordcount.core import count_lines, partition_lines, read_lines


def record(lines: list[str], word: str, threads: int, block: int) -> dict:
    ranges = partition_lines(len(lines), threads)
    spans = [[] for _ in range(threads)]
    partials = [0] * threads
    barrier = threading.Barrier(threads + 1)
    begin = 0.0

    def worker(index: int, start: int, stop: int) -> None:
        barrier.wait()  # start all workers together
        for first in range(start, stop, block):
            last = min(first + block, stop)
            t0 = perf_counter()
            partials[index] += count_lines(lines, first, last, word)
            spans[index].append((t0 - begin, perf_counter() - begin))

    workers = [threading.Thread(target=worker, args=(i, a, b), name=f"worker-{i + 1}")
               for i, (a, b) in enumerate(ranges)]
    for w in workers:
        w.start()
    begin = perf_counter()
    barrier.wait()
    for w in workers:
        w.join()
    gil = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
    return {"gil": "GIL on" if gil else "GIL off", "threads": threads,
            "total": sum(partials), "elapsed": perf_counter() - begin, "spans": spans}


def working_spans(spans: list) -> list[tuple[float, float]]:
    """Drop the waiting part of blocks that were paused by the scheduler.

    A block normally takes about the median block time. A block that took far
    longer was paused part-way (another thread held the GIL or the core), so
    only a median-sized working piece is drawn and the rest stays empty.
    """
    import statistics
    if not spans:
        return []
    typical = statistics.median(e - s for s, e in spans)
    drawn = []
    for s, e in spans:
        length = e - s
        drawn.append((s, typical if length > 3 * typical else max(length, 1e-6)))
    return drawn


def plot(files: list[Path], output: Path, window: float = 0.06) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    colors = ["#2A9D8F", "#E76F51", "#1F3A5F", "#E9C46A", "#8D99AE", "#6A4C93", "#43AA8B", "#F3722C"]
    fig, axes = plt.subplots(len(data), 1, figsize=(11, 1.4 + 0.55 * data[0]["threads"] * len(data)),
                             sharex=True, layout="constrained", squeeze=False)
    for ax, run in zip(axes[:, 0], data):
        for i, spans in enumerate(run["spans"]):
            ax.broken_barh([b for b in working_spans(spans) if b[0] < window],
                           (i - 0.38, 0.76), color=colors[i % len(colors)], linewidth=0)
        ax.set_yticks(range(run["threads"]), [f"worker-{i + 1}" for i in range(run["threads"])])
        ax.invert_yaxis()
        story = ("threads take turns: one works, the others wait" if run["gil"] == "GIL on"
                 else "threads work at the same time")
        ax.set_title(f"{run['gil']}: {story}  (whole run {run['elapsed']:.2f} s)",
                     loc="left", weight="bold")
        ax.grid(axis="x", alpha=0.3)
    axes[-1, 0].set_xlim(0, window)
    axes[-1, 0].set_xlabel(f"Time since start (seconds), first {window * 1000:.0f} ms; "
                           "white gaps = thread waiting")
    fig.savefig(output, dpi=200)
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--word", default="the")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--block", type=int, default=40, help="lines per recorded block (keep small: smaller than one 5 ms GIL turn)")
    parser.add_argument("--plot", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.plot:
        plot(args.plot, args.output)
        return
    if args.file is None:
        parser.error("--file is required unless --plot is used")
    result = record(read_lines(args.file), args.word, args.threads, args.block)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result), encoding="utf-8")
    print(f"{result['gil']}: {args.threads} threads, {result['elapsed']:.3f}s, "
          f"total={result['total']} -> {args.output}")


if __name__ == "__main__":
    main()
