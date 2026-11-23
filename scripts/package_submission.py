"""Build a compact submission ZIP without generated input or environment files."""

from pathlib import Path
import zipfile


root = Path(__file__).resolve().parents[1]
destination = root.parent / "COSC451_Parallel_Computing_Submission.zip"
files = [root / name for name in ("README.md", "pyproject.toml", "uv.lock", ".python-version", ".gitignore")]
for directory in ("src", "tests", "docs", "scripts", "results"):
    files.extend(path for path in (root / directory).rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
files.append(root / "data/sample.txt")
files += [root / "data/classroom.txt", root / "data/classroom.json"]
with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, Path(root.name) / path.relative_to(root))
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert not any("large.txt" in name or ".venv/" in name for name in archive.namelist())
    print(f"Packaged {len(archive.namelist())} files; CRC verification passed.")
print(destination)
print(f"Size: {destination.stat().st_size:,} bytes")
