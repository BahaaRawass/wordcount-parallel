"""Generate whole repeated lines with independently known counts."""

import argparse
import hashlib
import json
from pathlib import Path

LINE = b"the cat sees the dog. The other theme is there; the end.\n"


def generate(path: Path, mib: int) -> dict:
    if mib < 1:
        raise ValueError("size must be at least 1 MiB")
    repetitions = (mib * 1024 * 1024 + len(LINE) - 1) // len(LINE)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("wb") as output:
        remaining = repetitions
        while remaining:
            amount = min(remaining, 10000)
            block = LINE * amount
            output.write(block)
            digest.update(block)
            remaining -= amount
    metadata = {"bytes": repetitions * len(LINE), "lines": repetitions,
                "word": "the", "case_sensitive_count": repetitions * 3,
                "case_insensitive_count": repetitions * 4,
                "sha256": digest.hexdigest(), "line_ascii": LINE.decode("ascii")}
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path("data/large.txt"))
    parser.add_argument("--mib", type=int, default=50)
    args = parser.parse_args()
    try:
        metadata = generate(args.file, args.mib)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
