import sys
import webbrowser

if __name__ == '__main__':
    count = 0
    max = 1000
    if len(sys.argv) > 1:
        max = int(sys.argv[1])
    
    with open('../releases/backfill_new.txt', 'r') as f:
        lines = f.readlines()
        for line in lines:
            if count > max:
                break
            url = line.strip()
            webbrowser.open(url, new=0, autoraise=False)
            count += 1