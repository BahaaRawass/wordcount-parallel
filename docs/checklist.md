# Assignment requirement checklist

All paths below are relative to this document. Checked entries refer to completed files or executed evidence. The presentation deliverable requested here is a ten-slide outline with speaker notes, not a PowerPoint deck. Recording and Moodle upload are not part of this package.

## Research report

| Done | Requirement | File or section |
|---|---|---|
| [x] | Original academic Markdown report, approximately 6–8 pages equivalent | [report.md](report.md), approximately 3,760 words including references and tables; exact pagination depends on rendering |
| [x] | Define parallel and distributed computing and explain differences | Report section 2 and comparison table |
| [x] | Explain how one system can use both approaches | Report sections 2 and 3.2, hybrid cluster discussion |
| [x] | One real-world example of each | Report section 2: Blender GPU rendering and historical Google MapReduce |
| [x] | Work division, data exchange, and combination for each | Report sections 3.1 and 3.2 |
| [x] | One diagram for each, with PNG exports | ASCII diagrams in report; [parallel.png](figures/parallel.png), [distributed.png](figures/distributed.png); [export script](../scripts/diagrams.py) |
| [x] | At least two operating-system concepts | Report section 4: shared memory, scheduling/context switching, synchronization, IPC, partial failure |
| [x] | Concrete challenge and effect for parallel computing | Report sections 3.1 and 4.2: boundary ownership, lost updates, load imbalance |
| [x] | Concrete challenge and effect for distributed computing | Report section 4.3: delayed reply, retries, duplicate counting, recovery |
| [x] | At least three credible sources and consistent references | Eleven numbered references in report, including LLNL, OSTEP, the MapReduce paper, and Python documentation |

## Implementation and verification

| Done | Requirement | File or evidence |
|---|---|---|
| [x] | Use `uv init`, `uv add`, `uv sync`, and `uv run` | Executed setup documented in [README](../README.md); [sync log](../results/sync.txt) |
| [x] | Python 3.12 or newer pinned; reproducible environment | [.python-version](../.python-version), [pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock): CPython 3.13.15 |
| [x] | Simple Python implementation, standard-library core | [core.py](../src/wordcount/core.py); only direct extras are matplotlib and dev pytest |
| [x] | CLI with file, word, threads, trace, case mode | [cli.py](../src/wordcount/cli.py), README command examples |
| [x] | N chunks and N main-demo threads, safe word boundaries | `partition_lines` and `count_threaded` in core; report section 3.1 |
| [x] | Shared counter protected by `threading.Lock` | `count_threaded(..., combine="lock")`; [trace](../results/trace.txt) |
| [x] | Separate-result-slot variant with parent sum after join | `count_threaded(..., combine="slots")`; [slots trace](../results/slots-trace.txt) |
| [x] | Clearly labelled race demo with real evidence | [race.py](../src/wordcount/race.py); [captured output](../results/race.txt): expected 400, unsafe 100, locked 400 |
| [x] | Explain forced interleaving honestly | README race discussion; report section 4.2; no claim of spontaneous race frequency |
| [x] | Trace names/IDs, ranges, sizes, partials, start/end, total | [trace.txt](../results/trace.txt); README step-by-step explanation |
| [x] | Hand-checkable input with expected answer and actual comparison | [sample.txt](../data/sample.txt); README table: exact 7, case-insensitive 9; [verification log](../results/verification.txt) |
| [x] | Tests: one vs many, boundaries, empty file, case, substrings, excess threads | [test_core.py](../tests/test_core.py); [29 passing tests](../results/tests.txt) |
| [x] | Additional Unicode, no-final-newline, process, and failure checks | Same test module, including an independent regex oracle |
| [x] | Process comparison using `ProcessPoolExecutor` | `count_processes` in core; process CLI output and benchmark series |
| [x] | GIL, thread/process distinction, and implementation choice explained | Report sections 4.1, 4.3, 5, and 7; Python loop in timed path; no free-threaded measurements claimed |

## Experiment

| Done | Requirement | File or evidence |
|---|---|---|
| [x] | Write prediction before execution | [prediction.md](prediction.md), also embedded in [metadata](../results/metadata.json) |
| [x] | Generate a large file, avoid shipping/committing it | [generate.py](../src/wordcount/generate.py), [.gitignore](../.gitignore); 52,428,828 bytes; ZIP excludes it |
| [x] | Vary worker count through at least 2x physical cores | Workers 1, 2, 4, 8, 16; machine has 4 physical and 8 logical processors |
| [x] | Several repetitions, mean and spread | Three measured trials per setting; [raw.csv](../results/raw.csv), [summary.csv](../results/summary.csv), [warmup.csv](../results/warmup.csv) |
| [x] | Table, time chart, and speedup chart | [table.md](../results/table.md), [experiment.png](../results/experiment.png), report section 7 |
| [x] | Every reported count verified | 30 measured and 10 warm-up totals all equal 2,759,412; [benchmark log](../results/benchmark-log.txt) |
| [x] | Record CPU, cores, Python, and OS | [metadata.json](../results/metadata.json), report section 6 |
| [x] | Explain results without hiding lack of thread scaling | Report section 7, including large variation and limits of inference |
| [x] | Reproduction and timing scope | README experiment section and [demo-script.md](demo-script.md) |

## Presentation and delivery

| Done | Requirement | File or evidence |
|---|---|---|
| [x] | 8–10 slides with short speaker notes | [presentation-outline.md](presentation-outline.md), ten slides |
| [x] | Exact live commands and what to say | [demo-script.md](demo-script.md) |
| [x] | Eight likely questions and concise answers | [qa.md](qa.md) |
| [x] | Original code or attributed adaptations | README and report identify original code; conceptual sources are cited |
| [x] | Real output, no invented benchmarks | Captured logs, raw CSVs, metadata, source hashes, and integrity verification |
| [x] | Requirement mapping | This checklist |
| [x] | Portable submission package | `COSC451_Parallel_Computing_Submission.zip` in the parent folder; built by [package script](../scripts/package_submission.py) |

The supplied assignment also calls for each team member to contribute and participate in the presentation. Actual participation, any selected video recording and sharing permissions, and submission to Moodle remain activities for the team; they are not asserted as completed by these files.
