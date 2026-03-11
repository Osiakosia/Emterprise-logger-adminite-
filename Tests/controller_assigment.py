import os
import re

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))  # Skripto lokacija kaip root, gali keisti.
SEARCH_PATTERN = re.compile(r'controller\s*=\s*Controller\(')

def find_controller_creations(root_dir):
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith('.py'):
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, encoding='utf-8') as f:
                        for idx, line in enumerate(f, 1):
                            if SEARCH_PATTERN.search(line):
                                print(f"{fpath}:{idx}: {line.strip()}")
                except Exception as e:
                    print(f"!!! Error reading {fpath}: {e}")

if __name__ == "__main__":
    print("Ieškoma 'controller = Controller(' visuose .py failuose...")
    find_controller_creations(PROJECT_ROOT)