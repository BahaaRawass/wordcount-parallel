# Live demonstration script

Use PowerShell from the project folder. Commands below run in order. The short demo uses only the tiny input; allow a few seconds for process startup and tests. Present the saved experiment instead of waiting through the full benchmark in class.

## 1 Prepare before presenting

```powershell
Set-Location 'C:\Users\user\Desktop\College\Fall 2026\COSC451 - Operating Systems\Project\wordcount-parallel'
uv sync --locked
```

On another computer, change only the `Set-Location` path to the extracted folder. Synchronize before class while internet is available. Open the report, chart, and code in advance, and enlarge the terminal font.

**Say:** “We use a pinned Python version and locked dependencies. The counting algorithm itself uses the standard library.”

## 2 State the answer before executing

```powershell
Get-Content data/sample.txt
```

**Say:** “Only complete lowercase `the` tokens count. The six lines contribute 2, 0, 2, 1, 1, and 1, so we predict seven. `other` and `theme` are different tokens. Ignoring case would add two more.”

## 3 Establish one-thread correctness

```powershell
uv run wordcount --file data/sample.txt --word the --threads 1
```

**Say:** “The actual total is seven. This still creates one worker thread, which is also the baseline architecture in the experiment.”

## 4 Trace three workers

```powershell
uv run wordcount --file data/sample.txt --word the --threads 3 --trace
```

**Say:** “Worker 1 owns lines 1–2 and contributes two. Worker 2 owns lines 3–4 and contributes three. Worker 3 owns lines 5–6 and contributes two. The size is decoded characters. These start and end timestamps are milliseconds from dispatch. Main prints after joining, so output order follows chunks, not completion order.”

Point to `TOTAL=7`. **Say:** “Splitting only between lines means no token is cut or assigned twice. These thread IDs do not prove simultaneous execution. Tiny tasks may finish before the next thread starts.”

## 5 Change the combine method

```powershell
uv run wordcount --file data/sample.txt --word the --threads 3 --combine slots --trace
```

**Say:** “The result is still seven. Before, workers acquired a shared lock once to add a partial. Here each writes only its own slot; main sums after all joins. There is no application combine lock, but we still synchronize through completion.”

## 6 Check case handling and excess workers

```powershell
uv run wordcount --file data/sample.txt --word the --threads 8 --case-insensitive
```

**Say:** “Eight threads can handle six lines because empty chunks are valid. With case folding, the expected and actual total is nine.”

## 7 Make a race visible

```powershell
uv run wordcount-race --threads 4 --iterations 100
```

**Say:** “Four times one hundred should be four hundred. The controlled unsafe run returns one hundred, and the locked run returns four hundred. We deliberately force every worker to read before any writes. The GIL does not make that whole read/yield/write sequence atomic. This does not claim an unmodified increment fails every time.”

## 8 Show automated verification and the process comparison

```powershell
uv run pytest -q
uv run wordcount --file data/sample.txt --word the --threads 2 --backend processes
```

**Say:** “The saved run passed all 29 tests; a new run should also pass. This second command produces seven using separate interpreters. On a tiny file, startup dominates; we need the large-input experiment to assess performance.”

## 9 Present the experiment evidence

```powershell
Get-Content docs/prediction.md
Get-Content results/table.md
```

Display the already-open `results/experiment.png`.

**Say:** “We predicted little or no threading benefit. We held the input fixed and varied worker count, using three repetitions after warm-ups. Reading is excluded, but creation, process transfer, counting, and shutdown are included. Both speedup curves use the one-thread baseline. Threads show no convincing scaling. Eight processes had the lowest observed mean at 2.0059 seconds, about 2.424 times faster than the 4.8630-second baseline. Large error bars and changing conditions mean we should not overinterpret small differences.”

## 10 Optional full reproduction after the presentation

```powershell
uv run wordcount-generate --file data/large.txt --mib 50
uv run wordcount-experiment --file data/large.txt --workers 1 2 4 8 16 --repeats 3 --output results-live
```

Use an unused output directory; the runner refuses to replace existing raw measurements. These are the same generation and benchmark operations used for the saved run, with a new output path. Runtime depends on machine load. Every trial must return 2,759,412. The generated file is intentionally absent from the submission ZIP.

**Say:** “This command preserves every measured timing and checks every count. Fresh measurements may differ from the report; we should discuss them as a new run.”
