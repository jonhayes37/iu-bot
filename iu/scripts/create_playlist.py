import time
import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

scopes = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtubepartner",
]

api_service_name = "youtube"
api_version = "v3"
client_secrets_file = "client_secret.json"

def create_playlist(yt):
    request = yt.playlists().insert(
        part="snippet,status",
        body={
          "snippet": {
            "title": "2024 Releases"
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
    with open('../releases/2024_parsed_ids.txt', 'r') as f:
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
            except googleapiclient.errors.HttpError as e:
                if e.reason == 'failedPrecondition':
                    print(f'video {video_id} was unlisted')
                    continue
            except Exception as e:
                print(f'failed to add {video_id}: {e}')

            count += 1
            if count % 10 == 0:
                print(count)

# Disable OAuthlib's HTTPS verification when running locally.
# *DO NOT* leave this option enabled in production.
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
# Get credentials and create an API client
flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
    client_secrets_file, scopes)
credentials = flow.run_local_server()
youtube = googleapiclient.discovery.build(
    api_service_name, api_version, credentials=credentials)

# playlist = create_playlist(youtube)
playlist = 'PLO7u1j70-i0ONJtI4INav6qLM49MDafg1'
add_all_to_playlist(youtube, playlist)