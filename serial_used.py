import os
import re

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# Ieškome: SerialIO, SerialIO.open(, SerialIO.close(
PATTERNS = [
    r'SerialIO(\.open|\s|\()',
    r'SerialIO\.close\s*\(',
]

COMPILED = [re.compile(p) for p in PATTERNS]

def find_serialio_locations(root_dir):
    results = []
    for dirpath, _, files in os.walk(root_dir):
        for fname in files:
            if fname.endswith('.py'):
                file_path = os.path.join(dirpath, fname)
                try:
                    with open(file_path, encoding='utf-8') as f:
                        for idx, line in enumerate(f, 1):
                            for pat in COMPILED:
                                if pat.search(line):
                                    results.append({
                                        "file": file_path,
                                        "line": idx,
                                        "match": line.strip()
                                    })
                except Exception as e:
                    print(f"!!! Error reading {file_path}: {e}")

    return results

if __name__ == "__main__":
    print("Ieškoma SerialIO panaudojimų VISAME projekte...\n")
    hits = find_serialio_locations(PROJECT_ROOT)
    for h in hits:
        print(f"{h['file']}:{h['line']}: {h['match']}")