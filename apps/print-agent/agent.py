"""
Local print worker placeholder.

Run this on the machine that has printer drivers installed.
It can be extended to poll API jobs and print composed finals.
"""

import time


def main():
    print("Photo Booth print-agent started.")
    print("TODO: Poll /jobs/ready and print via pywin32.")
    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()
