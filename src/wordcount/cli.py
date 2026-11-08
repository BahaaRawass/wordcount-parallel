"""Projector-friendly command line interface."""

import argparse
from datetime import datetime, timezone
from time import perf_counter

from wordcount.core import count_processes, count_threaded, read_lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Count complete words in UTF-8 text")
    parser.add_argument("--file", required=True)
    parser.add_argument("--word", required=True)
    parser.add_argument("--threads", type=int, default=1, help="worker count for either backend")
    parser.add_argument("--combine", choices=("lock", "slots"), default="lock")
    parser.add_argument("--backend", choices=("threads", "processes"), default="threads")
    parser.add_argument("--case-insensitive", action="store_true")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    if args.backend == "processes" and args.trace:
        parser.error("--trace is supported by the main threads demo only")
    begin = perf_counter()
    try:
        lines = read_lines(args.file)
        loaded = perf_counter() - begin
        if args.backend == "threads":
            result = count_threaded(lines, args.word, args.threads, args.combine,
                                    args.case_insensitive, args.trace)
        else:
            result = count_processes(lines, args.word, args.threads, args.case_insensitive)
    except (OSError, UnicodeError, ValueError) as error:
        parser.error(str(error))
    print(f"Backend={args.backend} workers={args.threads} "
          f"combine={args.combine if args.backend == 'threads' else 'parent sum'}")
    print(f"Word={args.word!r} case_insensitive={args.case_insensitive} lines={len(lines)}")
    if args.trace:
        print("Line ranges are 1-based inclusive; timestamps are ms from dispatch.")
        print("Printed in chunk order after join; empty ranges have no lines.")
        for item in result.traces:
            line_range = (f"{item.start_line + 1}-{item.stop_line}"
                          if item.start_line < item.stop_line else "empty")
            print(f"{item.name} tid={item.native_id} lines={line_range} "
                  f"size={item.characters} chars partial={item.partial} "
                  f"start={item.start_seconds * 1000:.3f} "
                  f"end={item.end_seconds * 1000:.3f}")
        print("Reduction: " + " + ".join(map(str, result.partials)) + f" = {result.total}")
    print(f"TOTAL={result.total}")
    print(f"Read={loaded:.6f}s count/combine={result.elapsed_seconds:.6f}s")
    print(f"Finished UTC={datetime.now(timezone.utc).isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
