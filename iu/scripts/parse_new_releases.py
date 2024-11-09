import sys
import webbrowser

urls = []
releases = []

def parse_releases(browser):
    with open('../releases/2024.txt', 'r') as f:
        lines = f.readlines()
        for line in lines:
            parts = line.split(' // ')
            if parts[1] not in urls:
                releases.append((parts[0], parts[1]))
                urls.append(parts[1])

    sorted_releases = sorted(releases, key=lambda x: x[0])
    print(sorted_releases)
    with open('../releases/2024_parsed.txt', 'w+') as f:
        for release in sorted_releases:
            f.write(release[1])
            if browser:
                webbrowser.open(release[1], new=0, autoraise=False)
    
    return sorted_releases

if __name__ == '__main__':
    parse_releases(len(sys.argv) > 1)