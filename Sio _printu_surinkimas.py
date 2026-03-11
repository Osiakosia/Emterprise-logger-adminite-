import os
import re

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Ieškome print'ų, kurie turi sio.open/sio.close arba [DEBUG] žymą
PRINT_PATTERN = re.compile(r'print\(.*(sio\.open|sio\.close|DEBUG).*', re.IGNORECASE)

def collect_serial_logging(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith('.py'):
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, encoding='utf-8') as f:
                        for idx, line in enumerate(f, 1):
                            if PRINT_PATTERN.search(line):
                                print(f"{fpath}:{idx}: {line.strip()}")
                except Exception as e:
                    print(f"Klaida skaitant {fpath}: {e}")

if __name__ == "__main__":
    print("Collecting all Serial open/close log prints ...")
    collect_serial_logging(PROJECT_ROOT)