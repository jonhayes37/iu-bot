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

def parse_releases():
    with open('../releases/2025.txt', 'r') as f:
        lines = f.readlines()
        print(len(lines))
        for line in lines:
            parts = line.split(' // ')
            if parts[1] not in urls:
                releases.append((parts[0], parts[1]))
                urls.append(parts[1])

    sorted_releases = sorted(releases, key=lambda x: x[0])
    with open('../releases/2025_parsed.txt', 'w+') as f:
        with open('../releases/2025_parsed_ids.txt', 'w+') as f_id:
            for release in sorted_releases:
                f.write(release[1])
                f_id.write(f'{video_id_from_url(release[1])}\n')
        
    return sorted_releases

if __name__ == '__main__':
    parse_releases()