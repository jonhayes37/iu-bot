"""Script to open URLs from a file in the default web browser."""
import sys
import webbrowser

if __name__ == '__main__':
    COUNT = 0
    MAX = 1000
    if len(sys.argv) > 1:
        MAX = int(sys.argv[1])

    with open('../releases/backfill_new.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for line in lines:
            if COUNT > MAX:
                break
            url = line.strip()
            webbrowser.open(url, new=0, autoraise=False)
            COUNT += 1
