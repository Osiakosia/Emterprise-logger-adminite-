import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Paieškos raktai
PATTERNS = [
    "sio.open", "sio.close",
    "self.sio.open", "self.sio.close",
    "SerialIO.open", "SerialIO.close"
]

def matches_any_pattern(line):
    return any(pattern in line for pattern in PATTERNS)

def search_project(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith('.py'):
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, encoding='utf-8') as f:
                        for idx, line in enumerate(f, 1):
                            if matches_any_pattern(line):
                                print(f"{fpath}:{idx}: {line.strip()}")
                except Exception as e:
                    print(f"Klaida skaitant {fpath}: {e}")

if __name__ == "__main__":
    print(f"Searching for sio.open/close in {PROJECT_ROOT} ...")
    search_project(PROJECT_ROOT)