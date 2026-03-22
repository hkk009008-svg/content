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
    viral business case study topic for the day.
    """
    print("🧠 [PHASE 0] Researching the most lucrative business topic of the day...")
    
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
    You are an elite YouTube Shorts strategist prioritizing algorithmic virality and highly lucrative business content.
    
    {ab_memory}
    
    {live_trends}
    
    {global_sentiment}
    
    Your goal is to brainstorm the SINGLE most wild, intensely controversial, and profoundly mind-blowing business or entrepreneurship case study topic for today.
    
    You MUST craft a story that breaks the internet by aggressively matching the emotional state of the current live trends (whether inspiring or catastrophic):
    - [THE NEGATIVE EXTREME]: Deeply unethical corporate espionage, apocalyptic business failures, or manipulative marketing warfare.
    - [THE POSITIVE EXTREME]: Unbelievably genius innovations, massive viral underdog success stories, or hidden systems that are actively saving industries or making people rich.
    - [THE EDUCATIONAL REVELATION]: A profoundly brilliant, little-known business strategy or psychological framework that provides immense, positive value and actionable insight to the viewer.
    
    If the current scraped sentiment is fearful or angry, lean into the dark truths. If the current sentiment is optimistic, excited, or building, construct a deeply beneficial and awe-inspiring topic!
    
    The topic MUST be aggressive, wildly provocative, and deeply intriguing regardless of whether it is positive or negative.
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
