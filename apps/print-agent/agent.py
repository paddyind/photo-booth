"""
Local print worker placeholder (API job polling).

For **folder-based** printing of new finals under DATA_DIR, use **`scripts/print_watcher.py`**
and **`scripts/run-print-watcher.*`** instead (Docker + standalone).
"""

import time


def main():
    print("Photo Booth print-agent started.")
    print("TODO: Poll /jobs/ready and print via pywin32.")
    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()
