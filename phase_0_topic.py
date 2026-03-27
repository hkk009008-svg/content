import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", module="urllib3")
warnings.filterwarnings("ignore", category=UserWarning)

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Initialize the Gemini client 
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def get_used_topics() -> list:
    if not os.path.exists("used_topics.txt"):
        return []
    with open("used_topics.txt", "r") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def save_used_topic(topic: str):
    with open("used_topics.txt", "a") as f:
        f.write(topic + "\n")

def generate_trending_topic() -> str:
    """
    Acts as a YouTube Shorts strategist to brainstorm a highly lucrative, 
    viral philosophical/scientific topic for the day.
    """
    print("🧠 [PHASE 0] Researching fascinating universal/scientific topics of the day...")
    
    used_topics = get_used_topics()
    avoid_clause = ""
    if used_topics:
        recent_used = used_topics[-50:]
        avoid_clause = f"\n    CRITICAL: You MUST NOT pick any of these previously used topics, nor anything remotely similar:\n" + "\n".join([f"    - {t}" for t in recent_used]) + "\n"

    from phase_e_learning import get_top_performing_context, fetch_live_youtube_trends, fetch_external_market_sentiment
    ab_memory = get_top_performing_context()
    live_trends = fetch_live_youtube_trends()
    global_sentiment = fetch_external_market_sentiment()

    prompt = f"""
    You are an elite art-house film director and existential writer. You are deeply focused on uncovering human emotion, existential meaning, and universal connection.
    
    {ab_memory}
    
    {live_trends}
    
    {global_sentiment}
    
    Your goal is to brainstorm ONE profoundly beautiful, cinematic, and emotionally resonant topic for today. It must seamlessly match the emotional state of the current live data, but MUST focus entirely on profound, relatable human truths. It MUST fall into one of these cinematic narrative vectors:
    
    - [THE MEANING OF ORDINARY LIFE]: Finding breathtaking beauty, tranquility, and cinematic tension inside everyday moments (e.g., The profound silence of an empty childhood room, the poetry of a solitary morning coffee, the echo of rain against a window).
    - [THE WEIGHT OF LOVE & FAMILY]: Unpicking the complex, quiet sacrifices of parenthood, inherited memories, nostalgia, or the fleeting nature of human connection.
    - [EXISTENTIAL REFLECTION]: "Who am I?", the passage of time, the quiet struggle to understand our place in the universe, and the beauty of human imperfection.
    
    CRITICAL: Look at the current scraped market sentiment but synthesize it into a profoundly emotional concept. The vibe must remain deeply immersive and touching. Try to evoke the feeling: "Yes, I know exactly what that feels like. I have experienced it too." Do NOT use cheap engagement hooks, clickbait, or 'viral hacks.' Make it feel like an A24 masterpiece exploring the depths of the human condition.
    
    {avoid_clause}
    Provide ONLY the topic in 12 words or less. Do not include quotes, markdown formatting, or any extra text. Make it incredibly punchy.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=1.0, 
        ),
    )
    
    topic = response.text.strip().strip('"').strip("'")
    save_used_topic(topic)
    return topic

if __name__ == "__main__":
    topic = generate_trending_topic()
    print(f"\n🔥 Discovered Viral Topic: {topic}")
