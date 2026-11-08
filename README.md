# Exploring Parallel and Distributed Computing

COSC 451, Rafik Hariri University. The main demo counts complete words with Python `threading`. It shows line ownership, partial counts, a lock-protected reduction, a separate-slot reduction, and a controlled lost-update example. A secondary process implementation measures what changes when workers have separate interpreters.

## Start here

From PowerShell, enter this `wordcount-parallel` folder, then run:

```powershell
uv sync
uv run pytest -q
uv run wordcount --file data/sample.txt --word "the" --threads 3 --trace
```

Python **3.13.15** is pinned in `.python-version`; `uv` can install it if needed. `uv.lock` records the resolved packages. Runtime counting uses only the standard library; matplotlib is for figures and pytest is the development dependency. No virtual-environment activation is needed. Initial synchronization may need internet access. Dependencies pulled in by matplotlib are recorded in the lockfile; the scanner does not use NumPy.

The project was initialized with `uv init --package --python 3.12 wordcount-parallel`, then pinned to the available Python 3.13.15. Dependencies were added using `uv add matplotlib` and `uv add --dev pytest`; execution and verification use `uv run`. Both Python versions meet the requested 3.12-or-newer constraint. Do not rerun initialization on this finished project.

## What exactly is a word

A token is a maximal consecutive sequence of Unicode alphanumeric characters or underscores. Match the complete token. Thus `the,` matches `the`, but `other`, `theme`, `the2`, and `the_the` do not. Hyphens and apostrophes separate tokens: `the-the` has two matches. Case-sensitive matching is the default. `--case-insensitive` applies Unicode `casefold()` to each token and the target. It does not perform Unicode normalization, stemming, or language-specific segmentation; combining marks are separators under this definition. Targets containing punctuation or whitespace are rejected.

Files must be valid UTF-8. CRLF and LF line endings work; a final newline is optional. The program reads the entire file into a list of lines before counting, so it is an in-memory teaching demo. Do not modify that list during a count. The command reports read time separately.

## Hand-check and trace one task

`data/sample.txt` contains exactly these six lines:

```text
the cat and the dog.
The other theme is there.
the, THE; the!
another the
the
end the.
```

| Line  | Exact lowercase `the` | Case-insensitive `the` |
| ----- | --------------------: | ---------------------: |
| 1     |                     2 |                      2 |
| 2     |                     0 |                      1 |
| 3     |                     2 |                      3 |
| 4     |                     1 |                      1 |
| 5     |                     1 |                      1 |
| 6     |                     1 |                      1 |
| Total |                 **7** |                  **9** |

The three-thread trace in [results/trace.txt](results/trace.txt) is actual captured output. These lines were observed:

```text
worker-1 tid=29600 lines=1-2 size=47 chars partial=2 start=0.731 end=0.754
worker-2 tid=10036 lines=3-4 size=27 chars partial=3 start=1.052 end=1.066
worker-3 tid=26280 lines=5-6 size=13 chars partial=2 start=1.194 end=1.204
Reduction: 2 + 3 + 2 = 7
TOTAL=7
```

1. Main reads six complete lines and divides their indices into `[0,2)`, `[2,4)`, `[4,6)`. Displayed line numbers are 1-based and inclusive.
2. Each named OS thread scans its assigned lines. Chunk size is decoded characters including normalized newlines, not bytes.
3. Each worker computes a local integer. With `--combine lock`, it acquires the shared lock once and adds that integer to the total.
4. Main joins every worker, then prints the trace in chunk order. Start/end values are monotonic timestamps in milliseconds relative to dispatch, not wall-clock times.
5. The sum is seven, agreeing with the hand count. On this tiny input each worker finished before the next started. A trace of multiple threads is not evidence that their Python instructions ran simultaneously.

Thread IDs and timings vary on later runs; the line ranges and counts should stay the same. `Finished UTC` identifies the captured execution time.

## Commands for the two safe combine methods

```powershell
uv run wordcount --file data/sample.txt --word the --threads 1
uv run wordcount --file data/sample.txt --word the --threads 3 --combine lock --trace
uv run wordcount --file data/sample.txt --word the --threads 3 --combine slots --trace
uv run wordcount --file data/sample.txt --word the --threads 8 --case-insensitive
uv run wordcount --file data/sample.txt --word the --threads 2 --backend processes
uv run wordcount-race --threads 4 --iterations 100
```

Expected totals are 7, 7, 7, 9, and 7 respectively. These configurations were executed; the three-worker traces and race have dedicated logs, and [results/verification.txt](results/verification.txt) records the other CLI checks. Empty ranges are valid when workers outnumber lines; all requested threads are still created.

`slots` means no application-level combine lock: each worker writes one distinct result slot, and main sums after `join`. It is **not** a formal lock-free progress guarantee; joining and interpreter internals still synchronize.

Actual controlled-race output:

```text
CONTROLLED RACE DEMO: barriers enforce stale reads; sleep(0) yields.
This is not a claim that ordinary += fails on every CPython run.
Expected=400 unsafe=100 lost=300 locked=400
```

In the unsafe run every worker reads the old total before any writes, and all finish writing before the next round. Four attempted increments therefore preserve only one per round. The locked run holds the lock over read/yield/write. The barriers are scheduling aids, not a replacement for mutual exclusion. This demonstration does not deliberately corrupt the real counter.

## Reproduce the experiment

The prediction was written before execution in [docs/prediction.md](docs/prediction.md) and copied into run metadata. Generate the large input locally; it is excluded from version control and the submission ZIP.

```powershell
uv run wordcount-generate --file data/large.txt --mib 50
uv run wordcount-experiment --file data/large.txt --workers 1 2 4 8 16 --repeats 3 --output results-rerun
```

The saved first experiment uses `results`; choose a fresh output directory for each rerun. The runner refuses to overwrite `raw.csv`. Default worker counts extend through twice `os.cpu_count()` if `--workers` is omitted. On Windows the process pool is limited to 61 workers, so larger machines must supply a supported list. Here the five settings include 2x physical cores (8) and 2x logical processors (16).

The generator repeats a 57-byte line, rounding upward to a complete line. The saved input has 52,428,828 bytes, 919,804 lines, and exactly 2,759,412 lowercase matches. The JSON manifest supplies the expected total independently of the scanner and a SHA-256 integrity check.

Input read/decode is excluded from the benchmark clock. Partitioning, thread creation or fresh process-pool startup, process serialization, counting, reduction, joining, and shutdown are included. One warm-up for each backend/worker setting is saved separately. Three measured repetitions use shuffled configuration order with seed 451; tracing and plotting are outside timing. Each trial asserts the expected count. Error bars show sample standard deviation, not confidence intervals. Both chart series use the **one-thread mean** as their speedup denominator.

See [results/table.md](results/table.md), [results/experiment.png](results/experiment.png), and report section 7 for actual measurements. Raw timings, warm-ups, hardware and Python details, input hash, source hashes, and execution logs are included. The code does not pin CPU affinity, control power settings, or measure hardware counters.

## Source and deliverable map

| File                                                 | Purpose                                                          |
| ---------------------------------------------------- | ---------------------------------------------------------------- |
| `src/wordcount/core.py`                              | Scanner, line partitioning, two reductions, process comparison   |
| `src/wordcount/cli.py`                               | Arguments and readable trace output                              |
| `src/wordcount/race.py`                              | Deliberately forced lost update and locked correction            |
| `src/wordcount/generate.py`                          | Deterministic large file and known-count manifest                |
| `src/wordcount/experiment.py`                        | Repeated measurements, raw data, metadata, table, chart          |
| `tests/test_core.py`                                 | 29 passing tests, including independent regex cross-check        |
| [Research report](docs/report.md)                    | Definitions, diagrams, OS concepts, methods, results, references |
| [Presentation outline](docs/presentation-outline.md) | Ten slides with speaker notes                                    |
| [Demo script](docs/demo-script.md)                   | Exact live commands and explanation                              |
| [Q&A preparation](docs/qa.md)                        | Eight likely instructor questions                                |
| [Requirement checklist](docs/checklist.md)           | Requirement-to-evidence mapping                                  |

Regenerate architecture PNGs with `uv run scripts/diagrams.py`. All application code and diagrams were written for this project; no web code was copied. Conceptual sources are cited in the report. Matplotlib draws the figures; the core algorithm is a Python loop, not `str.count`, regex matching, or a NumPy operation. A test uses regex only as an independent correctness oracle.
