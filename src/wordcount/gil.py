"""Bonus experiment: the same threaded counter with the GIL on and with it off.

Run once with normal CPython (GIL on) and once with free-threaded CPython 3.13t
(GIL off), then plot both CSV files together:

  uv run wordcount-gil run --file data/large.txt --output results/gil-on.csv
  uv run --python 3.13t wordcount-gil run --file data/large.txt --output results/gil-off.csv
  uv run wordcount-gil plot results/gil-on.csv results/gil-off.csv --output results/gil.png
"""

import argparse
import csv
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

from wordcount.core import count_threaded, read_lines


def gil_enabled() -> bool:
    return sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True


def run(file: Path, word: str, workers: list[int], repeats: int, output: Path) -> list[dict]:
    lines = read_lines(file)
    expected = None
    manifest = file.with_suffix(".json")
    if manifest.exists():
        expected = json.loads(manifest.read_text(encoding="utf-8"))["case_sensitive_count"]
    label = "GIL on" if gil_enabled() else "GIL off"
    print(f"{label}: Python {platform.python_version()} "
          f"({'free-threaded build' if hasattr(sys, '_is_gil_enabled') and not gil_enabled() else 'standard build'}), "
          f"{os.cpu_count()} logical CPUs, {len(lines)} lines", flush=True)
    count_threaded(lines, word, 1)  # warm-up
    rows = []
    for count in workers:
        times = []
        for _ in range(repeats):
            begin = perf_counter()
            result = count_threaded(lines, word, count)
            times.append(perf_counter() - begin)
            if expected is not None and result.total != expected:
                raise AssertionError(f"wrong total {result.total}, expected {expected}")
        row = {"gil": label, "workers": count, "repeats": repeats,
               "median_seconds": statistics.median(times),
               "min_seconds": min(times), "max_seconds": max(times),
               "total": result.total}
        rows.append(row)
        print(f"{label} threads={count:2d} median={row['median_seconds']:.3f}s "
              f"min={row['min_seconds']:.3f}s max={row['max_seconds']:.3f}s "
              f"total={result.total}", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def plot(csv_files: list[Path], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), layout="constrained")
    colors = {"GIL on": "#8D99AE", "GIL off": "#2A9D8F"}
    for path in csv_files:
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        label = rows[0]["gil"]
        x = [int(r["workers"]) for r in rows]
        y = [float(r["median_seconds"]) for r in rows]
        base = y[0]
        axes[0].plot(x, y, marker="o", lw=2.5, label=label, color=colors.get(label))
        axes[1].plot(x, [base / v for v in y], marker="o", lw=2.5, label=label,
                     color=colors.get(label))
    axes[0].set(xlabel="Threads", ylabel="Median time (s), lower is better",
                title="Same code, GIL on vs off")
    axes[1].set(xlabel="Threads", ylabel="Speedup vs 1 thread of the same build",
                title="Speedup")
    axes[1].axhline(1, ls="--", color="grey", lw=1)
    for ax in axes:
        ax.set_xscale("log", base=2)
        ax.set_xticks(x, [str(v) for v in x])
        ax.grid(alpha=0.3)
        ax.legend(frameon=False)
    fig.savefig(output, dpi=200)
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--file", type=Path, required=True)
    r.add_argument("--word", default="the")
    r.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8])
    r.add_argument("--repeats", type=int, default=5)
    r.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("plot")
    p.add_argument("csv", type=Path, nargs="+")
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        run(args.file, args.word, args.workers, args.repeats, args.output)
    else:
        plot(args.csv, args.output)


if __name__ == "__main__":
    main()
