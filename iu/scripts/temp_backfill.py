import sys
import webbrowser

urls = []
releases = []

def video_id_from_url(url):
    url = url.strip()
    ending = url.split('/')[-1]
    if 'youtu.be' not in url:
        shortlink_parts = ending.split('?si=')
        if len(shortlink_parts) == 2:
            return shortlink_parts[0]
        else:
            if 'watch' in ending:
                watch_parts = ending.split('?v=')
                return watch_parts[1].split('&')[0]
            else:
                return ending
    else:
        return ending.split('?')[0]

def parse_urls(filename):
    urls = []
    with open(f'../releases/{filename}.txt', 'r') as f:
        lines = f.readlines()
        for line in lines:
            url = line.strip()
            urls.append(url)
        
    return urls

if __name__ == '__main__':
    subset_urls = parse_urls('2024_parsed')
    backfill_urls = parse_urls('2024_backfill_parsed')
    new_urls = []
    for url in backfill_urls:
        if url not in subset_urls:
            new_urls.append(url)

    with open(f'../releases/backfill_new.txt', 'w+') as f:
        for u in new_urls:
            f.write(f'{u}\n')