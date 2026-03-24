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
    You are an elite YouTube Shorts strategist prioritizing algorithmic virality and highly immersive philosophical/scientific content.
    
    {ab_memory}
    
    {live_trends}
    
    {global_sentiment}
    
    Your goal is to brainstorm ONE highly addictive, deep, or fascinating topic focused on low-cortisol visual wonders for today.
    
    You MUST craft a topic that seamlessly matches the emotional state of the current live trends but fits within these hyper-viral, low-anxiety vectors:
    - [MACRO-SCALE AWE]: Epically massive scales of deep space or deep time that reduce ego and validate insignificance (e.g., astrophotography, ancient geological time).
    - [HIDDEN TECHNICAL MECHANICS]: Deconstructing how complex systems work seamlessly internally (e.g., the aerodynamics of everyday objects, inside locks).
    - [DECONSTRUCTED DIGITAL PHYSICS]: Explaining the hidden mechanics of digital worlds (e.g., video game collision meshes, multi-agent logic).
    - [HYPER-MACRO SENSORY]: Extreme close-ups of fascinating textures and materials (e.g., ferrofluid, metallic liquids, microscopic alien flora).
    
    CRITICAL: Look at the current scraped sentiment. If the internet is stressed, lean into "Macro-Scale Awe". If people are curious, lean "Hidden Technical Mechanics". DO NOT fall back on generic listicles. The vibe must remain fascinating, visually heavy, and fundamentally calming/satisfying (the "Oasis" hook).
    
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
