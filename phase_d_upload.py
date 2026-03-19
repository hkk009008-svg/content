import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# This scope allows us to upload videos to your channel
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def authenticate_youtube():
    """Handles OAuth 2.0 authentication and saves the token for future runs."""
    print("🔐 [PHASE D] Authenticating with YouTube...")
    creds = None
    
    # Check if we already have a saved token from a previous run
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    # If no valid credentials, let the user log in via browser
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired Google token...")
            creds.refresh(Request())
        else:
            print("⚠️ First-time setup: Please check your browser to authorize the app...")
            # This requires client_secrets.json to be in your project folder!
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run (Autonomy!)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('youtube', 'v3', credentials=creds)

def upload_video(youtube, video_file, title, description, tags, thumbnail_file=None, publish_at=None):
    """Uploads the final .mp4 to YouTube as a Private Short and attaches a custom thumbnail."""
    print(f"🚀 [PHASE D] Preparing to upload: {video_file}")

    # Define the video metadata
    body = {
        "snippet": {
            "title": title,
            "description": description, 
            "tags": tags,
            "categoryId": "27" # 27 = Education. 
        },
        "status": {
            # CRITICAL: Upload as private (required initially for scheduled videos)
            "privacyStatus": "private", 
            "madeForKids": False,
            "selfDeclaredMadeForKids": False
        }
    }
    
    if publish_at:
        body["status"]["publishAt"] = publish_at
        print(f"⏰ Scheduling video to go public automatically at: {publish_at}")

    # Load the physical file
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype="video/mp4")

    # Create the API request
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    print("📤 Uploading to YouTube servers (this may take a moment)...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   Upload progress: {int(status.progress() * 100)}%")

    print(f"✅ Upload Complete! Video ID: {response['id']}")
    
    # --- NEW: Upload Thumbnail ---
    if thumbnail_file and os.path.exists(thumbnail_file):
        print(f"🖼️ Uploading custom thumbnail: {thumbnail_file}...")
        try:
            youtube.thumbnails().set(
                videoId=response['id'],
                media_body=MediaFileUpload(thumbnail_file, mimetype='image/png')
            ).execute()
            print("✅ Custom thumbnail applied successfully!")
        except Exception as e:
            print(f"⚠️ Could not upload thumbnail (Note: you may need to verify your YouTube account for custom thumbnails). Error: {e}")

    return response['id']

# Optional testing block
if __name__ == "__main__":
    print("Run this through main.py to execute the full upload sequence!")
