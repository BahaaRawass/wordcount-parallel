# Instructor Q&A preparation

1. **Why did adding threads not help?**  
   The tested CPython build has the GIL enabled, and our inner scanner is Python code. Threads therefore do not execute that bytecode simultaneously within this process. Worker-management costs and changing machine conditions can add time. Four threads were nominally 1.024× faster, which is too small relative to the spread to establish useful scaling.

2. **What happens without the lock? Does the GIL prevent races?**  
   Competing read/modify/write sequences can overwrite each other's updates. Our forced-interleaving demonstration returned 100 instead of 400; the locked version returned 400. Barriers and `sleep(0)` deliberately expose the interleaving. This is not evidence that ordinary `+=` must fail on every run, and the GIL is not a transaction around an arbitrary sequence of operations.

3. **How do you ensure a boundary does not lose or duplicate a word?**  
   We partition complete lines into adjacent half-open intervals. Their union covers every line once, with no overlap. Newlines separate tokens, so a word cannot straddle two assigned chunks. UTF-8 is decoded before partitioning. The final token is handled even without a final newline.

4. **Why can the slots version work without a combine mutex?**  
   Each worker owns a different slot and writes it once. Main joins all workers before summing. No two workers perform a competing read/modify/write of the same output element. “No combine lock” is more precise than claiming a formally lock-free algorithm: joins and interpreter operations still synchronize.

5. **Why do processes behave differently? Is that distributed computing?**  
   Each child has its own interpreter and can run on another core. That permits CPU parallelism but adds spawn and serialization costs. Our eight-process mean was 2.0059 s versus 4.8630 s for one thread, a 2.424× speedup. They all run on one machine, so this is local multiprocessing, not a networked distributed implementation.

6. **How would you make this distributed and handle a failed worker?**  
   Assign shards with unique task IDs, send their data or locations, receive partials, and track completion. Timeouts can trigger retries, but only one result per task should be accepted to prevent double counting. Coordinator recovery would need durable task state. Those mechanisms are a proposed extension, not implemented or benchmarked here.

7. **Are you counting substrings? What about punctuation and case?**  
   We count complete alphanumeric/underscore tokens. `the,` matches; `other`, `the2`, and `the_the` do not. Hyphens split tokens. Case-insensitive mode casefolds complete tokens. We do not perform Unicode normalization or language-specific word segmentation. The timed scanner uses Python loops; regex is only an independent test oracle.

8. **Can you conclude eight workers are optimal? What limits the experiment?**  
   No. Eight processes had the lowest mean in three trials, but the four- and eight-process ranges overlap. We used one laptop and uniform generated lines, did not control thermal state or background load, and observed large timing variation. A single long line would also create load imbalance. The measured clock excludes initial file reading but includes fresh worker startup, transfer, and shutdown; changing that scope would change the question.
