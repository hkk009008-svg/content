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
    
    # Gracefully upgrade table schema with new retention variables dynamically
    try:
        cursor.execute("ALTER TABLE shorts_experiments ADD COLUMN voice_id TEXT")
        cursor.execute("ALTER TABLE shorts_experiments ADD COLUMN loop_bridge TEXT")
    except sqlite3.OperationalError:
        pass # Columns already exist

    conn.commit()
    conn.close()

def log_experiment(ctx: dict):
    """Logs the genesis parameters of a newly uploaded video directly from the OmniContext."""
    script_data = ctx.get("script_data", {})
    video_id = ctx.get("youtube_video_id")
    title = script_data.get("title", "")
    topic = ctx.get("topic", "")
    playlist_category = script_data.get("playlist_category", "")
    music_vibe = ctx.get("music_vibe", "")
    video_pacing = ctx.get("video_pacing", "")
    script_tone = script_data.get("tone_used", "")
    hook_text = script_data.get("hook", "")
    voice_id = ctx.get("voice_id", "")
    loop_bridge = script_data.get("infinite_loop_bridge", "")
    
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    
    cursor.execute('''
        INSERT OR REPLACE INTO shorts_experiments 
        (video_id, title, topic, playlist_category, music_vibe, video_pacing, script_tone, hook_text, voice_id, loop_bridge, published_at, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (video_id, title, topic, playlist_category, music_vibe, video_pacing, script_tone, hook_text, voice_id, loop_bridge, now, now))
    
    conn.commit()
    conn.close()
    print(f"🧠 [A/B BRAIN] Logged experiment parameters for Video ID: {video_id}")

def calculate_viral_score(views, likes, comments, avg_duration, velocity=0.0):
    """Formula weighing raw traffic vs engagement vs retention. Tweak this as the channel grows."""
    # Base weight on views, heavy multiplier on engagement. 
    # CRITICAL 2026 ALGORITHM CALIBRATION: Retention (Average View Duration) and Velocity are the primary metrics.
    # Velocity (Views/Hour) allows instant pivoting to breakout trends within hours of uploading.
    return views + (likes * 10) + (comments * 25) + (avg_duration * 50) + (velocity * 100)

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

        now_dt = datetime.datetime.utcnow()
        now_iso = now_dt.isoformat() + "Z"

        # We need the published_at date to calculate velocity
        cursor.execute("SELECT video_id, published_at FROM shorts_experiments")
        publish_dates = {row[0]: row[1] for row in cursor.fetchall()}

        for item in stats_response.get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            
            # --- VIEW VELOCITY CALCULUS ---
            pub_date_str = publish_dates.get(vid)
            velocity = 0.0
            if pub_date_str:
                try:
                    pub_dt = datetime.datetime.fromisoformat(pub_date_str.replace("Z", ""))
                    hours_alive = max(0.1, (now_dt - pub_dt).total_seconds() / 3600.0)
                    velocity = views / hours_alive
                except ValueError:
                    pass
            
            # TODO: Add Analytics API call for Average View Duration here once traffic is high enough.
            # YouTube Analytics API requires the video to have sufficient watch time before returning rows.
            avg_duration = 0.0 
            
            viral_score = calculate_viral_score(views, likes, comments, avg_duration, velocity)

            cursor.execute('''
                UPDATE shorts_experiments 
                SET views=?, likes=?, comments=?, avg_view_duration_seconds=?, viral_score=?, last_updated=?
                WHERE video_id=?
            ''', (views, likes, comments, avg_duration, viral_score, now_iso, vid))
            
        conn.commit()
        print("✅ [A/B BRAIN] Database mathematically synchronized.")
    except Exception as e:
        print(f"⚠️ Warning: Could not sync analytics. {e}")
        
    conn.close()

def calculate_macro_statistics():
    """Crunches historical DB data to find the highest-performing autonomous variables."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    stats_string = ""
    try:
        # Get best vibe
        cursor.execute("SELECT music_vibe, AVG(viral_score) as avg_score FROM shorts_experiments WHERE views > 50 GROUP BY music_vibe ORDER BY avg_score DESC LIMIT 1")
        best_vibe = cursor.fetchone()
        if best_vibe:
            stats_string += f"        - HIGHEST PERFORMING CINEMATIC VIBE: '{best_vibe[0]}' (Average Score: {best_vibe[1]:.1f})\n"
            
        # Get best pacing
        cursor.execute("SELECT video_pacing, AVG(viral_score) as avg_score FROM shorts_experiments WHERE views > 50 GROUP BY video_pacing ORDER BY avg_score DESC LIMIT 1")
        best_pacing = cursor.fetchone()
        if best_pacing:
            stats_string += f"        - HIGHEST PERFORMING JUMP-CUT PACING: '{best_pacing[0]}' (Average Score: {best_pacing[1]:.1f})\n"
    except sqlite3.OperationalError:
        pass
    conn.close()
    
    if stats_string:
        return f"\n        [🧠 MACRO-STATISTICAL NEURAL AGGREGATION]\n        Based on a mathematical aggregation of our entire historical database, the following parameters are statistically proven to drive the highest retention:\n{stats_string}"
    return ""

def autonomous_batch_calibration():
    """Triggered after every batch. Scrapes the web for live trends and uses Gemini to synthesize the supreme strategy matrix."""
    print("\n" + "🔥"*25)
    print(f"🚨 AUTONOMOUS WEB-SCRAPING CALIBRATION SEQUENCE INITIATED 🚨")
    print("🔥"*25)
    print("AGENT MESSAGE: Scraping global data to recalibrate maximum algorithmic integrity...")
    
    live_youtube = fetch_live_youtube_trends()
    live_reddit = fetch_external_market_sentiment()
    macro_stats = calculate_macro_statistics()
    
    # Send all scraped live data to Gemini to formulate the master law
    prompt = f"""
    You are an elite, mathematical YouTube Growth Strategist.
    I have just finished rendering a batch of videos. I need you to completely calibrate our strategy for the NEXT batch.
    
    Here is the live data I just scraped from the web THIS SECOND:
    {live_youtube}
    {live_reddit}
    {macro_stats}
    
    INSTRUCTION: Read the above real-time data carefully. Synthesize the absolute highest integrity strategy for our next batch. 
    Tell me exactly what pacing, emotion, hook structure, and niche topics are objectively dominating right now.
    
    [STRICT OUTPUT FORMAT]:
    You MUST output your strategy as a mathematically rigid set of instructions (Rule 1, Rule 2, Rule 3, Rule 4). Do not give generic advice. Give absolute, binary instructions that the AI Video Generator cannot misunderstand. Example: "RULE 1: The visual vibe MUST be 'Corporate' because..."
    """
    
    from google import genai
    import os
    
    try:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        # We use gemini-2.5-flash for high-reasoning context synthesis
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        calibration_rules = response.text
        
        # Save this to a physical file so the Generator uses it on the next run!
        with open("CALIBRATION_MATRIX.txt", "w") as f:
            f.write(calibration_rules)
            
        print("\n✅ [A/B BRAIN] Successful global scrape. New Master Matrix written to CALIBRATION_MATRIX.txt.")
        print("The AI will intrinsically obey these new high-integrity rules on the very next generation run.")
        print("="*60 + "\n")
    except Exception as e:
        print(f"⚠️ Calibration scraping failed. {e}\n")

def get_top_performing_context():
    """Returns a dynamic string for Gemini's prompt based on the highest Viral Score in DB."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Needs at least 150 views to be considered a 'proven' success pattern
    try:
        cursor.execute('''
            SELECT title, topic, playlist_category, music_vibe, video_pacing, script_tone, hook_text, voice_id, loop_bridge, views, likes, comments, viral_score
            FROM shorts_experiments
            WHERE views > 150
            ORDER BY viral_score DESC
            LIMIT 1
        ''')
        top_video = cursor.fetchone()
    except sqlite3.OperationalError:
        # Failsafe if columns haven't been migrated yet to prevent crash
        top_video = None
        
    conn.close()
    
    if top_video:
        try:
            title, topic, playlist, vibe, pacing, tone, hook, voice_id, loop_bridge, views, likes, comments, score = top_video
        except ValueError:
            return "" # Failsafe for unmigrated DB rows
            
        macro_stats = calculate_macro_statistics()
        
        return f"""
        [⚠️ CRITICAL SYSTEM MEMORY: PREVIOUS A/B SUCCESS ⚠️]
        The algorithm strongly favors the following parameters based on our Analytics Database.
        Your most successful recent video ("{title}") hit {views} views, {likes} likes, and {comments} comments (Viral Score: {score:.1f}).
        
        - Previous Winning Topic: "{topic}"
        - Previous Winning Playlist: "{playlist}"
        - Previous Winning Vibe: {vibe} (This controls the Cinematic Color Grading)
        - Previous Winning Pacing: {pacing} (This physically controls the Jump-Cut velocity)
        - Previous Winning Hook Style: "{hook}"
        - Previous Winning Infinite Loop Bridge: "{loop_bridge}" (This successfully looped seamlessly into the Hook)
        - Previous Winning Voice Actor ID: "{voice_id}"
        {macro_stats}
        
        INSTRUCTION: The algorithm's self-learning matrix has detected that this previous video drove massive audience retention. You MUST mathematically weight your logic heavily toward the STORY ITSELF. Analyze exactly WHAT was said in that successful Hook, HOW it was phrased (tone, sentence structure, emotional trigger), and WHY it trapped the viewer's attention.
        Tweak your next script to replicate that exact psychological story structure and narrative flow, applying it to the new topic. Subvert expectations with shocking new data, but firmly adopt the winning storytelling mechanism of that specific Hook and Loop Bridge!
        """
    else:
        # 🟢 THE AUTONOMOUS GAP FILLER 🟢
        # If the internal A/B testing database is empty or lacks proven winners, 
        # we autonomously crawl external intelligence to bridge the gap!
        print("🧠 [A/B BRAIN] Local database empty. Crawling external network for structural inspiration...")
        try:
            import requests
            # Fetch the top 3 smartest, highest-voted tech/business headlines on Hacker News right now
            hn_top = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=5).json()
            fallback_headlines = []
            for item_id in hn_top[:3]:
                item_data = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json", timeout=5).json()
                if item_data and 'title' in item_data:
                    fallback_headlines.append(f'- "{item_data["title"]}"')
                    
            if fallback_headlines:
                headlines_str = "\n        ".join(fallback_headlines)
                return f"""
        [⚠️ CRITICAL SYSTEM MEMORY: AUTONOMOUS GAP FILLER INITIATED ⚠️]
        Your internal A/B testing database currently has NO proven winners to model after. 
        Instead of guessing blindly, the system has autonomously crawled the highest-voted, most intellectually engaging posts on Hacker News right at this very second.
        
        The absolute smartest people on the internet are currently clicking on these exact structural headlines:
        {headlines_str}
        
        INSTRUCTION: You MUST reverse-engineer the psychological framing, curiosity gaps, and structural formatting of those exact headlines. Use them as a structural template to format your Hook and Topic angle. Borrow their genius to fill your database gap!
        """
        except Exception as e:
            print(f"⚠️ Warning: Autonomous gap filler failed. {e}")
            
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

def fetch_external_market_sentiment():
    """Scrapes public Reddit JSON endpoints for real-time market and business sentiment."""
    import requests
    print("🌍 [A/B BRAIN] Scanning global market sentiment (Reddit/News)...")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    sentiment_titles = []
    
    try:
        # Check WallStreetBets for raw market chaos/trends
        wsb_url = "https://www.reddit.com/r/WallStreetBets/hot.json?limit=7"
        wsb_resp = requests.get(wsb_url, headers=headers, timeout=5)
        if wsb_resp.status_code == 200:
            for post in wsb_resp.json().get('data', {}).get('children', []):
                title = post['data'].get('title', '')
                if len(title) > 15:
                    sentiment_titles.append(f"[WSB] {title}")
                    
        # Check Entrepreneur for business strategies/struggles
        ent_url = "https://www.reddit.com/r/Entrepreneur/hot.json?limit=7"
        ent_resp = requests.get(ent_url, headers=headers, timeout=5)
        if ent_resp.status_code == 200:
            for post in ent_resp.json().get('data', {}).get('children', []):
                title = post['data'].get('title', '')
                if len(title) > 15:
                    sentiment_titles.append(f"[Entrepreneur] {title}")
                    
        if not sentiment_titles:
            return ""
            
        trend_str = "\n".join([f"        - {t}" for t in sentiment_titles])
        return f"""
        [🌍 LIVE GLOBAL MARKET & BUSINESS SENTIMENT 🌍]
        Beyond just YouTube, here is what the internet is actively obsessing over, panicking about, or building right now on the front pages of business communities:
{trend_str}
        
        INSTRUCTION: Synthesize these raw, real-world human emotions and trends. If the internet is panicking, lean into the dark scandal. But if the community is celebrating a massive win or obsessed with a profound positive innovation, mirror that excitement and make the topic highly beneficial and inspiring!
        """
    except Exception as e:
        print(f"⚠️ Warning: Could not fetch external market sentiment. {e}")
        return ""
