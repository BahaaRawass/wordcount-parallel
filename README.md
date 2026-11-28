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

## Source map

| File                              | Purpose                                                            |
| --------------------------------- | ------------------------------------------------------------------ |
| `src/wordcount/core.py`           | Scanner, line partitioning, two reductions, process comparison     |
| `src/wordcount/cli.py`            | Arguments and readable trace output                                |
| `src/wordcount/race.py`           | Deliberately forced lost update and locked correction              |
| `src/wordcount/generate.py`       | Deterministic large file and known-count manifest                  |
| `src/wordcount/experiment.py`     | Repeated measurements, raw data, metadata, table, chart            |
| `src/wordcount/gil.py`            | Bonus: the same threaded counter with the GIL on and off           |
| `src/wordcount/natural_race.py`   | Bonus: a race condition that happens on its own without the GIL    |
| `src/wordcount/timeline.py`       | Bonus: timeline chart of when each thread is really working        |
| `src/wordcount/distributed.py`    | Bonus: coordinator and workers over TCP sockets, crash recovery    |
| `src/wordcount/cluster.py`        | Bonus: classroom cluster task queue with leases and dashboard      |
| `src/wordcount/cluster_pages.py`  | Bonus: the phone page and the projector dashboard                  |
| `tests/test_core.py`, `tests/test_cluster.py` | 41 passing tests, including an independent regex cross-check |
| `docs/prediction.md`              | The prediction written before the experiment (read by the experiment command) |
| `results/`                        | Saved outputs of every run: timings, traces, race, bonus demos     |

The research report and the presentation slides are submitted separately. All application code was written for this project; no web code was copied. Matplotlib draws the charts; the core algorithm is a Python loop, not `str.count`, regex matching, or a NumPy operation. A test uses regex only as an independent correctness oracle.

## Bonus features (added after the first submission draft)

These extend the required demo. None of them change the original counter.

### 1. Turn the GIL off: same code, real thread speedup

Python 3.13 ships an official experimental free-threaded build (`3.13t`) with no GIL. We run the unchanged `count_threaded` on both builds.

**How the no-GIL commands work.** The project's chart library (matplotlib, with NumPy and Pillow) has no ready-made packages for free-threaded Python 3.13, so `uv run --python 3.13t wordcount-...` fails while trying to build them. The bonus experiments do not need those libraries (only the plotting step does, and that runs on normal Python). So the no-GIL commands run our code directly: `--no-project` skips installing the project's packages, and `PYTHONPATH=src` lets Python find our code. Run these once per PowerShell window before the no-GIL commands:

```powershell
uv python install 3.13t
$env:PYTHONPATH = "src"
```

```powershell
uv run wordcount-generate --file data/large.txt --mib 50
uv run wordcount-gil run --file data/large.txt --workers 1 2 4 8 --repeats 5 --output results/bonus/gil-on.csv
uv run --no-project --python 3.13t python -m wordcount.gil run --file data/large.txt --workers 1 2 4 8 --repeats 5 --output results/bonus/gil-off.csv
uv run wordcount-gil plot results/bonus/gil-on.csv results/bonus/gil-off.csv --output results/bonus/gil.png
```

### 2. A natural race condition (no barriers, no sleeps)

```powershell
uv run wordcount-natural-race                                            # GIL on: usually 0 lost
uv run --no-project --python 3.13t python -m wordcount.natural_race      # GIL off: hundreds of thousands lost
```

### 3. Thread timeline (who is really running)

```powershell
uv run wordcount-timeline --file data/large.txt --threads 2 --output results/bonus/timeline-gil-on.json
uv run --no-project --python 3.13t python -m wordcount.timeline --file data/large.txt --threads 2 --output results/bonus/timeline-gil-off.json
uv run wordcount-timeline --plot results/bonus/timeline-gil-on.json results/bonus/timeline-gil-off.json --output results/bonus/timeline.png
```

### 4. Distributed version over sockets, with failure recovery

A coordinator splits the file into line-range tasks and sends each one as a JSON message over TCP to a worker process. Workers reply with their partial count. If a worker crashes or stops answering within the timeout, its task is sent to another worker, and each task ID is accepted only once.

Simulated on one laptop (separate processes talking through sockets, as the brief allows):

```powershell
uv run wordcount-coordinator --file data/sample.txt --word the --local 3
uv run wordcount-coordinator --file data/sample.txt --word the --local 3 --crash-one --delay 0.3
```

On real laptops (all on the same phone hotspot):

```powershell
# on each worker laptop (allow Python through the Windows firewall when asked)
ipconfig                         # note the IPv4 address
uv run wordcount-worker --name laptop-B
# on the coordinator laptop
uv run wordcount-coordinator --file data/sample.txt --word the --workers 192.168.43.12 192.168.43.15 --timeout 3
```

During the demo, close one worker window or turn off its Wi-Fi: the coordinator prints `FAIL ... task goes back in the queue`, resends it, and still prints `TOTAL=7`.

Saved outputs from our runs are in `results/bonus/`.

### 5. Classroom cluster: the class becomes the computer (fault-tolerant task queue)

The laptop runs a small web server. Classmates on the same Wi-Fi open the address in their phone browser and each phone becomes a worker. A live dashboard on the projector shows every task (waiting, running, done), which device has it, the running total, and every message.

It works like real job queues (Amazon SQS, Celery):

* **Workers pull tasks.** A worker asks for a task, counts its lines, and sends back the partial count.
* **Leases.** A worker may hold a task for `--lease` seconds. If no answer arrives in time (tab closed, phone locked, Wi-Fi lost), the task goes back in the queue and another worker takes it.
* **Counted exactly once.** A task can be *executed* twice (the "dead" worker may still answer later), but its result is *counted* only once: the first result wins and later ones are shown as `DUPLICATE IGNORED`.
* **Checked answer.** The coordinator knows the correct total in advance and shows ✓ or ✗ at the end.

```powershell
# 1. Practise alone: 3 worker processes on this laptop, one crashes, one answers late
uv run wordcount-cluster --local 3 --crash-one --late-one
#    open http://localhost:8000/dashboard and press Start

# 2. In class
uv run wordcount-cluster --file data/classroom.txt --word the --tasks 20 --lease 5 --pace 1.5
#    projector: http://localhost:8000/dashboard
#    classmates open the "Phones and laptops" address printed in the terminal, type a name, press Join
#    press Start on the dashboard; ask one person to press "Leave" (or close the tab) mid-task

# 3. Another laptop can join from a terminal instead of a browser
uv run wordcount-cluster-worker --server http://192.168.1.20:8000 --name laptop-B
uv run wordcount-cluster-worker --server http://192.168.1.20:8000 --name slow-laptop --late 8
```

**Count any file.** The dashboard has a *Job* panel (only on the coordinator laptop). Choose a `.txt` or Word `.docx` file, type the word, set the number of tasks, tick *ignore upper/lower case* if wanted, and press **Load**. The queue resets with the new file, phones that already joined stay connected, and the dashboard shows the new expected total. Leave the file empty to change only the word. In a Word file each paragraph (including table cells and text inside shapes) becomes one line; old `.doc` files must be saved as `.docx` first. Answers that belong to a previous file are ignored, so changing the file mid-run can never mix two counts.

The same works from the terminal: `uv run wordcount-cluster --file "C:\path\essay.docx" --word data`.

`--pace` makes each worker wait a moment per task so the audience can follow; use `--pace 0` for full speed. `Start` and `Restart` only work from the coordinator laptop itself.

**Before class:** when Windows asks, allow Python on *private* networks. Many university Wi-Fi networks block phone-to-laptop traffic; if phones cannot open the page, turn on a phone hotspot, connect the laptop and the phones to it, and restart the command (the printed address changes).

Saved run: `results/bonus/cluster-demo.txt` and `results/bonus/cluster-dashboard.png`.
