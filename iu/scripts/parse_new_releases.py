"""
Docstring for iu.scripts.parse_new_releases
"""
from .temp_backfill import video_id_from_url

urls = []
releases = []


def parse_releases():
    with open('../releases/2025.txt', 'r', encoding='utf-8') as f_name:
        lines = f_name.readlines()
        print(len(lines))
        for line in lines:
            parts = line.split(' // ')
            if parts[1] not in urls:
                releases.append((parts[0], parts[1]))
                urls.append(parts[1])

    sorted_releases = sorted(releases, key=lambda x: x[0])
    with open('../releases/2025_parsed.txt', 'w+', encoding='utf-8') as f_name:
        with open('../releases/2025_parsed_ids.txt', 'w+', encoding='utf-8') as f_id:
            for release in sorted_releases:
                f_name.write(release[1])
                f_id.write(f'{video_id_from_url(release[1])}\n')

    return sorted_releases

if __name__ == '__main__':
    parse_releases()
