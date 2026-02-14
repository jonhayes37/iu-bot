"""
Docstring for iu.scripts.create_playlist
"""
import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

scopes = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtubepartner",
]

API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
CLIENT_SECRETS_FILE = "client_secret.json"

def create_playlist(yt):
    request = yt.playlists().insert(
        part="snippet,status",
        body={
          "snippet": {
            "title": "2025 Releases"
          },
          "status": {
            "privacyStatus": "unlisted"
          }
        }
    )
    response = request.execute()

    print(response)
    return response.get('id')

def add_all_to_playlist(yt, playlist_id):
    count = 0
    with open('../releases/2025_parsed_ids.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for line in lines:
            video_id = line.strip()
            try:
                request = yt.playlistItems().insert(
                    part="snippet,status",
                    body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id
                        }
                    }
                    }
                )
                request.execute()
            except googleapiclient.errors.HttpError as ex:
                if ex.reason == 'failedPrecondition':
                    print(f'video {video_id} was unlisted')
                    continue
                else:
                    print(f'failed to add {video_id}: {ex}')

            count += 1
            if count % 10 == 0:
                print(count)

# Disable OAuthlib's HTTPS verification when running locally.
# *DO NOT* leave this option enabled in production.
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
# Get credentials and create an API client
flow = google_auth_oauthlib.flow.InstalledAppFlow.from_CLIENT_SECRETS_FILE(
    CLIENT_SECRETS_FILE, scopes)
credentials = flow.run_local_server()
youtube = googleapiclient.discovery.build(
    API_SERVICE_NAME, API_VERSION, credentials=credentials)

# playlist = create_playlist(youtube)
PLAYLIST = 'PLO7u1j70-i0Om0ggJ84rHi8z9Q9uK2YvQ'
add_all_to_playlist(youtube, PLAYLIST)
