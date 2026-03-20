import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Initialize the Gemini client 
# (Requires GOOGLE_API_KEY environment variable to be set)
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_shorts_script(topic: str) -> dict:
    """
    Generates a highly-engaging 60-second YouTube Shorts script.
    Enforces a strict JSON response.
    """
    import random
    from phase_e_learning import get_top_performing_context, fetch_live_youtube_trends
    ab_memory = get_top_performing_context()
    live_trends = fetch_live_youtube_trends()
    
    styles = ["an aggressive, high-energy tone", "a mysterious, secretive tone", "a highly analytical, numbers-focused tone", "a storytelling, historical tone", "a contrarian, 'everything you know is wrong' tone"]
    tone = random.choice(styles)
    
    prompt = f"""
    You are an expert YouTube Shorts scriptwriter in the Business & Entrepreneurship niche. 
    
    {ab_memory}
    
    {live_trends}
    
    Write a highly engaging 60-second case study about: "{topic}".
    Use {tone}. Make sure the angle, hook, and body are completely unique and different from standard explanations!
    
    [CRITICAL HOOK RULE - MAXIMIZE RETENTION]: 
    Your first 3 seconds MUST be a hyper-aggressive pattern interrupt. Start immediately with a shocking contradiction, a massive monetary figure, or a deeply controversial statement to instantly hack viewer retention. Do NOT use standard greetings.
    
    [THE OPEN LOOP TRAP - ADDICTIVENESS BOOST]:
    You MUST tease a massive, mind-blowing secret at the very beginning of the script, but deliberately REFUSE to reveal the answer until the final 5 seconds. This forces the viewer to stay until the end.
    
    [RUTHLESS PACING & VISCERAL STORYTELLING]:
    The script must flow exactly like a high-tension thriller. You must physically cut out ALL corporate fluff and gracefully eradicate all weak filler words ('basically', 'essentially', 'in conclusion'). Use extremely punchy, visceral, and aggressive power words. Speak directly to human greed, fear, curiosity, or shock.
    
    [OMNISCIENT RESEARCH & THOUGHT-PROVOKING RESOLUTION]:
    You must execute profound, deep-level research on the topic. Do NOT just surface generic Wikipedia facts. Unearth obscure historical connections, hidden insider motivations, or deeply psychological warfare strategies. The final payoff must NOT just be a boring business summary—it must be a profoundly captivating, thought-provoking, philosophical, and mind-bending resolution that leaves the viewer questioning everything or completely shifting their worldview.
    
    Rules:
    1. Hook: Start with a contrarian, mind-blowing, or secretive business fact (under 3 seconds) that opens a massive psychological loop.
    2. Body: Explain the business model, the massive failure, or the genius strategy in 3 punchy, hyper-addictive bullet points. Use exact numbers or dollar amounts if possible.
    3. The Payoff (DENSE & COMPACT): Close the open loop at the very end with a satisfying, mind-bending conclusion. The payoff MUST be brutally efficient—deliver the final philosophical truth in exactly one or two razor-sharp, unforgettable sentences. Do NOT ramble or explain.
    4. The Infinite Loop CTA: You MUST craft the final sentence of the script so it grammatically and flawlessly flows backward into the very first word of the Hook. Do NOT say 'Subscribe'. For example, if your Hook is 'Netflix is actually a debt machine.', the final sentence MUST cleanly end with '...and that is the terrifying reason why...' so when the video automatically loops, the viewer flawlessly hears: '...and that is the terrifying reason why Netflix is actually a debt machine.'
    5. Length & Pacing: You MUST dictate the pacing STRICTLY based on the tone of the story. If the story is 'aggressive' or 'upbeat', you MUST choose 'fast' pacing (~140 words) to maximize retention. If the story is 'suspense' or 'corporate', choose 'moderate' pacing (~125 words). ONLY choose 'relaxed' pacing if the story is 'lofi' and requires a deeply emotional, slow-burn psychological delivery (under 110 words). NEVER use 'relaxed' pacing for high-energy topics.
    6. The Neural Camera Director: For every single AI Image Prompt, you MUST explicitly assign a cinematic camera motion. If the sentence is aggressive, use 'dolly_in_rapid' or 'zoom_in_fast'. If building suspense, use 'pan_up_crane' or 'zoom_out_slow'. 
    7. CRITICAL VISUAL-CAMERA SYNERGY: The physical image prompt MUST mathematically accommodate the camera motion! If you choose 'pan_up_crane', the image prompt MUST describe a towering vertical subject (like a skyscraper or deep chasm). If you choose 'zoom_out_slow', the prompt MUST explicitly describe a vast, wide environment. The generated image MUST physically support how the camera will physically move through it. Do NOT exclusively use macro close-ups.
    """
    
    # We define the expected JSON schema to guarantee the output structure
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "A catchy title for the video"},
            "hook": {"type": "STRING", "description": "The opening sentence"},
            "body_paragraphs": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "3 punchy bullet points"
            },
            "infinite_loop_bridge": {"type": "STRING", "description": "The ending sentence designed to natively loop back into the hook."},
            "ai_image_prompts": {
                "type": "ARRAY", 
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "prompt": {"type": "STRING", "description": "The exact Midjourney-style text prompt for the visual."},
                        "camera": {
                            "type": "STRING",
                            "enum": ["zoom_in_slow", "zoom_out_slow", "zoom_in_fast", "pan_right", "pan_left", "pan_up_crane", "pan_down", "static_drone", "dolly_in_rapid"],
                            "description": "Select the exact cinematic camera motion that matches the emotional velocity of the spoken audio."
                        }
                    },
                    "required": ["prompt", "camera"]
                },
                "description": "EXACTLY 12 highly detailed visual prompt objects perfectly tied to the text."
            },
            "youtube_description": {
                "type": "STRING",
                "description": "An SEO-optimized 3-sentence YouTube video description loaded with keywords."
            },
            "youtube_tags": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "EXACTLY 15 highly-targeted, viral YouTube tags relating to the topic."
            },
            "music_vibe": {
                "type": "STRING",
                "enum": ["suspense", "corporate", "lofi", "upbeat", "aggressive"],
                "description": "Select the emotional vibe of the music that perfectly matches the topic of this case study."
            },
            "video_pacing": {
                "type": "STRING",
                "enum": ["fast", "moderate", "relaxed"],
                "description": "Select the pacing. MUST be 'fast' if upbeat/aggressive. MUST be 'moderate' if suspense/corporate. MUST be 'relaxed' uniquely for lofi storytelling."
            },
            "playlist_category": {
                "type": "STRING",
                "description": "A high-level YouTube playlist name this video belongs to (e.g. 'Business Secrets', 'Tech History', 'Marketing Psychology'). Max 3 words."
            }
        },
        "required": ["title", "hook", "body_paragraphs", "infinite_loop_bridge", "ai_image_prompts", "youtube_description", "youtube_tags", "music_vibe", "video_pacing", "playlist_category"]
    }
    
    # Call the Gemini 2.5 Flash model
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.99,
        ),
    )
    
    # Parse and return the JSON string into a Python dictionary
    parsed_json = json.loads(response.text)
    # Inject the randomly selected tone for the experiment logger
    parsed_json['tone_used'] = tone
    return parsed_json

# --- Testing the Module ---
if __name__ == "__main__":
    # A classic, high-performing business case study topic:
    trending_topic = "How McDonald's actually makes its money from real estate, not selling burgers."
    
    print(f"Generating script for: {trending_topic}\n")
    
    try:
        final_script = generate_shorts_script(trending_topic)
        print(json.dumps(final_script, indent=4))
    except Exception as e:
        print(f"Error generating script: {e}")
        print("Make sure you have set the GOOGLE_API_KEY environment variable and installed google-genai.")
