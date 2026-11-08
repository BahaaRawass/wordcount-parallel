"""Audit saved evidence and local Markdown links without rerunning benchmarks."""

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


root = Path(__file__).resolve().parents[1]
metadata = json.loads((root / "results/metadata.json").read_text(encoding="utf-8"))
raw = list(csv.DictReader((root / "results/raw.csv").open(encoding="utf-8")))
warmups = list(csv.DictReader((root / "results/warmup.csv").open(encoding="utf-8")))
summary = list(csv.DictReader((root / "results/summary.csv").open(encoding="utf-8")))
assert len(raw) == 30 and len(warmups) == 10 and len(summary) == 10
assert all(int(row["total"]) == 2759412 for row in raw + warmups)
baseline = statistics.mean(float(row["seconds"]) for row in raw
                           if row["backend"] == "threads" and row["workers"] == "1")
for row in summary:
    times = [float(trial["seconds"]) for trial in raw
             if (trial["backend"], trial["workers"]) == (row["backend"], row["workers"])]
    assert len(times) == 3
    checks = {"mean_seconds": statistics.mean(times),
              "stdev_seconds": statistics.stdev(times), "min_seconds": min(times),
              "max_seconds": max(times), "speedup_vs_one_thread": baseline / statistics.mean(times)}
    assert all(math.isclose(float(row[key]), value, rel_tol=1e-12) for key, value in checks.items())
    report_row = (f"| {row['backend']} | {row['workers']} | {checks['mean_seconds']:.4f} | "
                  f"{checks['stdev_seconds']:.4f} | {checks['min_seconds']:.4f} | "
                  f"{checks['max_seconds']:.4f} | {checks['speedup_vs_one_thread']:.3f} |")
    assert report_row in (root / "docs/report.md").read_text(encoding="utf-8")
for name, expected in metadata["source_sha256"].items():
    actual = hashlib.sha256((root / "src/wordcount" / name).read_bytes()).hexdigest()
    assert actual == expected, f"source changed after benchmark: {name}"
assert metadata["prediction"] == (root / "docs/prediction.md").read_text(encoding="utf-8")
documents = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
links = 0
for path in documents:
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"\bTODO\b|Add your description|final results section", text)
    for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        if target.startswith(("http:", "https:", "#")):
            continue
        assert (path.parent / target.split("#")[0]).exists(), f"broken link: {path.name}: {target}"
        links += 1
print("PASS: 30 measured trials and 10 warm-ups have the expected count.")
print("PASS: all ten summary rows independently recompute from raw timings and match the report.")
print("PASS: measured source hashes and pre-run prediction match the delivered files.")
print(f"PASS: {links} local Markdown links resolve; no unfinished-content markers.")
print("Report word count (whitespace-separated):", len((root / "docs/report.md").read_text(encoding="utf-8").split()))
