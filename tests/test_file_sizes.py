from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".sh"}
EXCLUDED_PARTS = {".git", ".venv", "coverage", "dist", "node_modules"}
MAX_LINES = 300


def test_maintained_source_files_stay_under_300_lines():
    oversized = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts):
            continue
        line_count = len(path.read_bytes().splitlines())
        if line_count > MAX_LINES:
            oversized.append(f"{path.relative_to(ROOT)}: {line_count}")
    assert not oversized, "Files over 300 lines:\n" + "\n".join(sorted(oversized))
