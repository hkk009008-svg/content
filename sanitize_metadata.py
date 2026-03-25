import os
import re
import time
import argparse
from phase_d_upload import authenticate_youtube

# The strings that triggered the spam classifiers
FOOTER_FOOTPRINTS = [
    "[Link]",
    "[YOUR_AFFILIATE_LINK]",
    "[YOUR ACTUAL LINK HERE! Edit line 104 in main.py]",
    "Start your own business today:",
    "Build Your Unfair Advantage ->",
    "Scale Your Business Automations ->",
    "🚀",
    "💼",
    "---"
]

def sanitize_description(desc):
    lines = desc.split('\n')
    cleaned_lines = []
    
    # Simple strategy: keep lines until we hit the footprint separator or specific affiliate link boilerplate
    for line in lines:
        if any(footprint in line for footprint in FOOTER_FOOTPRINTS):
            continue
            
        # Also remove exact matches for empty tags if they got left over
        if line.strip() in ["#shorts #business #finance", "#shorts"]:
            continue
            
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines).strip()

def sanitize_metadata(dry_run=True):
    print("🚀 TARGETING: Metadata Sanitization.")
    print(f"🛠️  MODE: {'[DRY RUN]' if dry_run else '[LIVE EXECUTION]'}")
    
    youtube = authenticate_youtube()
    
    try:
        # Get the 'uploads' playlist ID for the authenticated channel
        channel_response = youtube.channels().list(
            mine=True,
            part="contentDetails"
        ).execute()
        
        uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        print(f"📂 Found Uploads Playlist ID: {uploads_playlist_id}")
        
    except Exception as e:
        print(f"❌ Failed to retrieve channel details: {e}")
        return

    next_page_token = None
    sanitized_count = 0
    scanned_count = 0
    
    while True:
        playlist_response = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet",
            maxResults=50,
            pageToken=next_page_token
        ).execute()
        
        items = playlist_response.get("items", [])
        if not items:
            break
            
        for item in items:
            video_id = item["snippet"]["resourceId"]["videoId"]
            title = item["snippet"]["title"]
            description = item["snippet"]["description"]
            scanned_count += 1
            
            # Check if description has footprint
            needs_sanitization = any(fp in description for fp in FOOTER_FOOTPRINTS)
            
            if needs_sanitization:
                print(f"\n⚠️ Footprint Detected in [{video_id}] '{title}'")
                
                new_description = sanitize_description(description)
                
                if dry_run:
                    print(f"--- OLD PREVIEW ---\n{description}\n-------------------")
                    print(f"--- NEW PREVIEW ---\n{new_description}\n-------------------")
                else:
                    try:
                        # Fetch the full snippet to preserve tags and category
                        video_response = youtube.videos().list(
                            part="snippet",
                            id=video_id
                        ).execute()
                        
                        video_snippet = video_response["items"][0]["snippet"]
                        video_snippet["description"] = new_description
                        
                        youtube.videos().update(
                            part="snippet",
                            body={
                                "id": video_id,
                                "snippet": video_snippet
                            }
                        ).execute()
                        
                        print(f"✅ Executed Sanitization for [{video_id}]")
                        sanitized_count += 1
                        time.sleep(2) # Throttle to avoid velocity bans
                        
                    except Exception as e:
                        print(f"❌ Failed to update {video_id}: {e}")
                        
        next_page_token = playlist_response.get("nextPageToken")
        if not next_page_token:
            break
            
    print(f"\n🏁 Audit Complete. Scanned: {scanned_count} | Sanitized: {sanitized_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Metadata Sanitization Pass")
    parser.add_argument("--execute", action="store_true", help="Run the actual updates instead of dry-run")
    args = parser.parse_args()
    
    sanitize_metadata(dry_run=not args.execute)
