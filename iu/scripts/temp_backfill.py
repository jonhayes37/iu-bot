"""Script for backfilling YouTube video URLs."""

urls = []
releases = []

def video_id_from_url(video_url):
    clean_url = video_url.strip()
    ending = clean_url.split('/')[-1]
    if 'youtu.be' not in clean_url:
        shortlink_parts = ending.split('?si=')
        if len(shortlink_parts) == 2:
            return shortlink_parts[0]

        if 'watch' in ending:
            watch_parts = ending.split('?v=')
            return watch_parts[1].split('&')[0]

        return ending

    return ending.split('?')[0]

def parse_urls(filename):
    cur_urls = []
    with open(f'../releases/{filename}.txt', 'r', encoding='utf-8') as f_name:
        lines = f_name.readlines()
        for line in lines:
            cur_url = line.strip()
            cur_urls.append(cur_url)

    return cur_urls

if __name__ == '__main__':
    subset_urls = parse_urls('2024_parsed')
    backfill_urls = parse_urls('2024_backfill_parsed')
    new_urls = []
    for url in backfill_urls:
        if url not in subset_urls:
            new_urls.append(url)

    with open('../releases/backfill_new.txt', 'w+', encoding='utf-8') as f:
        for u in new_urls:
            f.write(f'{u}\n')
