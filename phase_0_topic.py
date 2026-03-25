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
    You are an elite YouTube Shorts strategist aggressively optimizing for the 25-35 male demographic. They value strategic thinking, uncovering hidden systems, brutal efficiency, power dynamics, and financial/technological leverage.
    
    {ab_memory}
    
    {live_trends}
    
    {global_sentiment}
    
    Your goal is to brainstorm ONE profoundly fascinating topic for today. It must seamlessly match the emotional state of the current live trends, but MUST utilize REVERSE PSYCHOLOGY by framing the topic as a paradigm-shattering truth, a contrarian reality, or a forbidden system the average person is fundamentally wrong about. It MUST fall into one of these highly-lucrative narrative vectors:
    
    - [THE ILLUSION OF CONTROL & MASSIVE STRATEGY]: Deconstructing hidden psychological tactics, global economic machines, or brilliant power plays (e.g., How McDonald's is a real estate empire, the psychology of casino floor designs, how your attention is algorithmically harvested).
    - [FORBIDDEN ECONOMIES & THE UGLY TRUTH]: Unsolved mechanical mysteries, the profound scale of industrial megastructures, or ruthless logistics of the modern world (e.g., The terrifying acoustics of ancient temples, the hidden multi-billion dollar economy of deep-sea cables).
    - [CYBERNETICS & MASSIVE SCALE INEVITABILITY]: The terrifying but beautiful reality of artificial intelligence, planetary-scale data centers, or future tech leverage (e.g., Dyson spheres, how glowing fiber optics silently run the global economy while we sleep).
    
    CRITICAL: Look at the current scraped sentiment. The vibe must remain deeply immersive, cool, highly-cinematic, and fundamentally strategic. Utilize reverse-psychology—make the topic sound like something the system doesn't want them to think about. DO NOT use cheap, hyper-emotional, or fluffy framing. Make it feel like a premium, gritty, contrarian documentary.
    
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
