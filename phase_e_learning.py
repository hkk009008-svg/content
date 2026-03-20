import sqlite3
import datetime
import os

DB_FILE = "experiments.db"

def init_db():
    """Initializes the SQLite database if it doesn't already exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create the experiments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shorts_experiments (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            topic TEXT,
            playlist_category TEXT,
            music_vibe TEXT,
            video_pacing TEXT,
            script_tone TEXT,
            hook_text TEXT,
            published_at TEXT,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            avg_view_duration_seconds REAL DEFAULT 0.0,
            viral_score REAL DEFAULT 0.0,
            last_updated TEXT
        )
    ''')
    conn.commit()
    conn.close()

def log_experiment(video_id, title, topic, playlist_category, music_vibe, video_pacing, script_tone, hook_text):
    """Logs the genesis parameters of a newly uploaded video."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    
    cursor.execute('''
        INSERT OR REPLACE INTO shorts_experiments 
        (video_id, title, topic, playlist_category, music_vibe, video_pacing, script_tone, hook_text, published_at, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (video_id, title, topic, playlist_category, music_vibe, video_pacing, script_tone, hook_text, now, now))
    
    conn.commit()
    conn.close()
    print(f"🧠 [A/B BRAIN] Logged experiment parameters for Video ID: {video_id}")

def calculate_viral_score(views, likes, comments, avg_duration):
    """Formula weighing raw traffic vs engagement vs retention. Tweak this as the channel grows."""
    # Base weight on views, heavy multiplier on likes/comments, and bonus for long retention
    return views + (likes * 10) + (comments * 25) + (avg_duration * 5)

def fetch_and_update_analytics(youtube_auth):
    """
    Pulls the latest analytics from the YouTube API for all logged videos.
    Requires an authenticated youtube service object (from phase_d_upload).
    """
    init_db()
    print("📈 [A/B BRAIN] Syncing analytics for past experiments...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT video_id FROM shorts_experiments")
    rows = cursor.fetchall()
    
    if not rows:
        print("   No previous videos to analyze yet.")
        conn.close()
        return

    # Extract all IDs as a comma-separated string for a batch Data API request
    video_ids = ",".join([row[0] for row in rows])
    
    try:
        # First, grab basic stats (Views, Likes, Comments) via the Data API (v3)
        stats_response = youtube_auth.videos().list(
            part="statistics",
            id=video_ids
        ).execute()

        now = datetime.datetime.utcnow().isoformat() + "Z"

        for item in stats_response.get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            
            # TODO: Add Analytics API call for Average View Duration here once traffic is high enough.
            # YouTube Analytics API requires the video to have sufficient watch time before returning rows.
            avg_duration = 0.0 
            
            viral_score = calculate_viral_score(views, likes, comments, avg_duration)

            cursor.execute('''
                UPDATE shorts_experiments 
                SET views=?, likes=?, comments=?, avg_view_duration_seconds=?, viral_score=?, last_updated=?
                WHERE video_id=?
            ''', (views, likes, comments, avg_duration, viral_score, now, vid))
            
        conn.commit()
        print("✅ [A/B BRAIN] Database mathematically synchronized.")
    except Exception as e:
        print(f"⚠️ Warning: Could not sync analytics. {e}")
        
    conn.close()

def check_calibration_milestone():
    """Checks the database to see if we hit a multiple of 10 uploads and prints a terminal alert."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM shorts_experiments')
    count = cursor.fetchone()[0]
    conn.close()
    
    if count > 0 and count % 10 == 0:
        print("\n" + "🔥"*25)
        print(f"🚨 CALIBRATION PROTOCOL TRIGGERED: {count} VIDEOS LOGGED 🚨")
        print("🔥"*25)
        print("AGENT MESSAGE: Please pause the engine and paste your current YouTube")
        print("Studio Engagements Dashboard to your AI Architect immediately!")
        print("We need to mathematically recalibrate the jump-cuts, Neon vibes,")
        print("and visual psychology based on your new retention data.")
        print("="*60 + "\n")

def get_top_performing_context():
    """Returns a dynamic string for Gemini's prompt based on the highest Viral Score in DB."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Needs at least 150 views to be considered a 'proven' success pattern
    cursor.execute('''
        SELECT title, topic, playlist_category, music_vibe, video_pacing, script_tone, hook_text, views, likes, comments, viral_score
        FROM shorts_experiments
        WHERE views > 150
        ORDER BY viral_score DESC
        LIMIT 1
    ''')
    top_video = cursor.fetchone()
    conn.close()
    
    if top_video:
        title, topic, playlist, vibe, pacing, tone, hook, views, likes, comments, score = top_video
        return f"""
        [⚠️ CRITICAL SYSTEM MEMORY: PREVIOUS A/B SUCCESS ⚠️]
        The algorithm strongly favors the following parameters based on our Analytics Database.
        Your most successful recent video ("{title}") hit {views} views, {likes} likes, and {comments} comments (Viral Score: {score:.1f}).
        
        - Previous Winning Topic: "{topic}"
        - Previous Winning Playlist: "{playlist}"
        - Previous Winning Vibe: {vibe} (This mathematically controls the Neon Flashes and Podcast Sound Mixing)
        - Previous Winning Pacing: {pacing} (This chemically controls the exact Jump-Cut speed from 1.5s to 3.0s)
        - Previous Winning Script Tone: {tone} (This controlled the delivery of the Open Loop trap)
        - Previous Winning Hook Style: "{hook}"
        
        INSTRUCTION: Because these physical visual/audio components were mathematically proven to maximize the "Stayed to Watch" retention metric on this audience, generate a script that perfectly synchronizes with these exact optimal parameters! Subvert their semantic expectations by generating completely new, shocking data that hits the exact opposite emotional notes, but firmly wrap it inside this exact winning pacing and aesthetic framework!
        """
    else:
        # If no proven winners yet, let the AI act entirely random to explore the possibility space.
        return ""

def fetch_live_youtube_trends():
    """Pulls the highest-performing Shorts from the last 14 days to analyze current algorithm favorability."""
    from phase_d_upload import authenticate_youtube
    import datetime
    
    youtube = authenticate_youtube()
    two_weeks_ago = (datetime.datetime.utcnow() - datetime.timedelta(days=14)).isoformat() + "Z"
    
    print("📡 [A/B BRAIN] Harvesting live YouTube algorithm trends for the business niche...")
    try:
        search_response = youtube.search().list(
            q="business entrepreneurship #shorts",
            part="snippet",
            maxResults=10,
            order="viewCount",
            publishedAfter=two_weeks_ago,
            type="video"
        ).execute()
        
        trending_titles = [item['snippet']['title'] for item in search_response.get('items', [])]
        
        if not trending_titles:
            return ""
            
        trend_str = "\n".join([f"        - {t}" for t in trending_titles])
        return f"""
        [🔥 LIVE YOUTUBE ALGORITHM TRENDS 🔥]
        The YouTube algorithm is currently heavily favoring and ranking videos with the following recent viral titles:
{trend_str}
        
        INSTRUCTION: Deeply analyze the keywords, structures, and psychological hooks of these viral titles. Weight your generated output to strictly align with what the algorithm is currently rewarding in search rankings!
        """
    except Exception as e:
        print(f"⚠️ Warning: Could not fetch live trends. {e}")
        return ""
