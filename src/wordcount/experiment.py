"""Repeat the fixed workload, preserve raw timings, and plot measured results."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from time import perf_counter

from wordcount.core import count_processes, count_threaded, read_lines


def machine_info() -> dict:
    info = {"python": sys.version, "implementation": platform.python_implementation(),
            "os": platform.platform(), "logical_processors": os.cpu_count(),
            "cpu_model": platform.processor(), "physical_cores": None,
            "gil_enabled": sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else None}
    if os.name == "nt":
        command = ("Get-CimInstance Win32_Processor | "
                   "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json")
        try:
            result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                                    capture_output=True, text=True, check=True, timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            cpus = json.loads(result.stdout)
            cpus = cpus if isinstance(cpus, list) else [cpus]
            info["cpu_model"] = "; ".join(cpu["Name"] for cpu in cpus)
            info["physical_cores"] = sum(cpu["NumberOfCores"] for cpu in cpus)
            info["hardware_source"] = "Windows Win32_Processor CIM"
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            info["hardware_query_error"] = str(error)
    return info


def summarize(rows: list[dict]) -> list[dict]:
    baseline = statistics.mean(row["seconds"] for row in rows
                               if row["backend"] == "threads" and row["workers"] == 1)
    summary = []
    for backend in ("threads", "processes"):
        counts = sorted({row["workers"] for row in rows if row["backend"] == backend})
        for workers in counts:
            times = [row["seconds"] for row in rows
                     if row["backend"] == backend and row["workers"] == workers]
            mean = statistics.mean(times)
            summary.append({"backend": backend, "workers": workers, "repeats": len(times),
                            "mean_seconds": mean, "stdev_seconds": statistics.stdev(times),
                            "min_seconds": min(times), "max_seconds": max(times),
                            "speedup_vs_one_thread": baseline / mean})
    return summary


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot(summary: list[dict], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    for backend, color in (("threads", "#2166ac"), ("processes", "#b35806")):
        rows = [row for row in summary if row["backend"] == backend]
        x = [row["workers"] for row in rows]
        axes[0].errorbar(x, [row["mean_seconds"] for row in rows],
                         yerr=[row["stdev_seconds"] for row in rows],
                         marker="o", capsize=4, label=backend, color=color)
        axes[1].plot(x, [row["speedup_vs_one_thread"] for row in rows],
                     marker="o", label=backend, color=color)
    axes[0].set(ylabel="Wall time (seconds)", title="Mean with sample standard deviation")
    axes[1].set(ylabel="Speedup relative to one thread", title="Same workload and baseline")
    axes[1].axhline(1, color="gray", linestyle="--", linewidth=1)
    ticks = sorted({row["workers"] for row in summary})
    for axis in axes:
        axis.set_xscale("log", base=2)
        axis.set_xticks(ticks, labels=[str(tick) for tick in ticks])
        axis.set_xlabel("Workers")
        axis.grid(alpha=0.2)
        axis.legend()
    fig.suptitle("Whole-word count on fixed UTF-8 input; fresh workers each trial")
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path("data/large.txt"))
    parser.add_argument("--workers", type=int, nargs="+")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("at least two repetitions are needed for sample standard deviation")
    workers = args.workers
    if workers is None:
        limit = 2 * (os.cpu_count() or 1)
        workers = [1]
        while workers[-1] * 2 < limit:
            workers.append(workers[-1] * 2)
        workers.append(limit)
    workers = sorted(set(workers))
    if min(workers) < 1 or 1 not in workers:
        parser.error("worker counts must be positive and include 1 for the baseline")
    if os.name == "nt" and max(workers) > 61:
        parser.error("Windows process comparison supports at most 61 workers; supply --workers")
    args.output.mkdir(parents=True, exist_ok=True)
    # Do not accidentally overwrite a completed or partially completed experiment.
    if (args.output / "raw.csv").exists():
        parser.error("output already contains raw.csv; choose a new --output directory")
    manifest = json.loads(args.file.with_suffix(".json").read_text(encoding="utf-8"))
    with args.file.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != manifest["sha256"]:
        parser.error("input hash differs from its generator manifest")
    load_start = perf_counter()
    lines = read_lines(args.file)
    read_seconds = perf_counter() - load_start
    expected = manifest["case_sensitive_count"]
    metadata = {"started_utc": datetime.now(timezone.utc).isoformat(),
                "machine": machine_info(), "input": manifest, "workers": workers,
                "repeats": args.repeats, "seed": 451, "read_seconds_excluded": read_seconds,
                "word": "the", "case_insensitive": False, "combine": "lock",
                "timing": "outer perf_counter: partition, worker creation, dispatch, count, reduction, shutdown; preloaded input",
                "prediction": Path("docs/prediction.md").read_text(encoding="utf-8"),
                "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in Path(__file__).parent.glob("*.py")}}
    metadata_path = args.output / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata["machine"], indent=2), flush=True)
    print(f"Input={manifest['bytes']} bytes expected={expected}; read excluded={read_seconds:.3f}s", flush=True)
    configurations = [(backend, n) for backend in ("threads", "processes") for n in workers]

    def trial(backend: str, count: int) -> tuple[float, int]:
        begin = perf_counter()
        if backend == "threads":
            result = count_threaded(lines, "the", count, combine="lock")
        else:
            result = count_processes(lines, "the", count)
        elapsed = perf_counter() - begin
        if result.total != expected:
            raise RuntimeError(f"incorrect count: {result.total}, expected {expected}")
        return elapsed, result.total

    warmups = []
    for backend, count in configurations:
        elapsed, total = trial(backend, count)
        warmups.append({"backend": backend, "workers": count, "seconds": elapsed, "total": total})
        print(f"warmup {backend:9s} n={count:2d} {elapsed:.6f}s total={total}", flush=True)
    write_csv(args.output / "warmup.csv", warmups)
    rows = []
    rng = random.Random(451)
    for repeat in range(1, args.repeats + 1):
        order = configurations.copy()
        rng.shuffle(order)
        for backend, count in order:
            elapsed, total = trial(backend, count)
            rows.append({"order": len(rows) + 1, "repeat": repeat, "backend": backend,
                         "workers": count, "seconds": elapsed, "total": total})
            write_csv(args.output / "raw.csv", rows)
            print(f"trial {repeat} {backend:9s} n={count:2d} {elapsed:.6f}s total={total}", flush=True)
    summary = summarize(rows)
    write_csv(args.output / "summary.csv", summary)
    table = ["| Backend | Workers | Mean s | SD s | Min s | Max s | Speedup vs 1 thread |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in summary:
        table.append(f"| {row['backend']} | {row['workers']} | {row['mean_seconds']:.4f} | "
                     f"{row['stdev_seconds']:.4f} | {row['min_seconds']:.4f} | "
                     f"{row['max_seconds']:.4f} | {row['speedup_vs_one_thread']:.3f} |")
    (args.output / "table.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    plot(summary, args.output / "experiment.png")
    print("\n".join(table), flush=True)


if __name__ == "__main__":
    main()
