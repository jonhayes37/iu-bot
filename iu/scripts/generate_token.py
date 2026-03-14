import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# The specific permission we need to manage YouTube playlists
SCOPES = ['https://www.googleapis.com/auth/youtube']

def generate():
    creds = None

    # Check if we already have a token
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # If no valid credentials, let's log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This triggers the browser popup!
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open('token.json', 'w', encoding='utf-8') as token_file:
            token_file.write(creds.to_json())

    print("✅ token.json successfully generated!")

if __name__ == '__main__':
    generate()
