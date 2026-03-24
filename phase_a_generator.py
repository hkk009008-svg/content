import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Initialize the Gemini client 
# (Requires GOOGLE_API_KEY environment variable to be set)
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_shorts_script(ctx: dict) -> bool:
    """
    Generates a highly-engaging 60-second YouTube Shorts script directly into the OmniContext.
    Enforces a strict JSON response.
    """
    topic = ctx["topic"]
    language = ctx.get("language", "English")
    print(f"\n✍️ [PHASE A] Writing highly-retentive script in {language.upper()} for topic: {topic}")
    import random
    from phase_e_learning import get_top_performing_context, fetch_live_youtube_trends
    ab_memory = get_top_performing_context()
    live_trends = fetch_live_youtube_trends()
    
    import os
    calibration_matrix = ""
    if os.path.exists("CALIBRATION_MATRIX.txt"):
        with open("CALIBRATION_MATRIX.txt", "r") as f:
            raw_matrix = f.read()
            calibration_matrix = f"\n[🔥 THE OMNI-CALIBRATION MATRIX 🔥]\n{raw_matrix}\n"
    
    master_storyteller_matrix = {
        "The Forensics": {
            "name": "The Forensic Investigator (Analytical Deep-Dive)",
            "aesthetic": "Cold, calculated, and terrifyingly precise. Emphasize the hidden mechanisms behind massive systems. Break down business models, historical mysteries, or tech like a master detective solving a global crime.",
            "hook": "The Sudden Reveal: Instantly expose a massive lie or a hidden truth about a system everyone takes for granted.",
            "pacing": "Methodical, sharp, authoritative, and brilliantly analytical."
        },
        "The Machiavellian": {
            "name": "The Machiavellian Mastermind (Power & Strategy)",
            "aesthetic": "Ruthless efficiency, leverage, and global power plays. Focus on the psychology of manipulation, brilliant marketing, and how empires—corporate or historical—control the masses.",
            "hook": "The Power Shift: Dramatically reveal how the viewer is currently being manipulated or outsmarted by the subject.",
            "pacing": "Calculated, dominant, slightly sinister, and unbroken."
        },
        "The Cyber-Prophet": {
            "name": "The Cyber-Prophet (Futuristic Inevitability)",
            "aesthetic": "Neon, data-driven, and slightly dystopian. Treat the subject as an inevitable mathematical future. Focus on terrifyingly beautiful cybernetics, global networks, and unstoppable technological shifts.",
            "hook": "The Ticking Clock: A heavy, inevitable realization that the future has already quietly arrived while they weren't looking.",
            "pacing": "Sleek, rapid, electric, and unstoppable."
        },
        "The Archivist": {
            "name": "The Secret Archivist (Forbidden History)",
            "aesthetic": "Dusty, secretive, forbidden knowledge. Treat the subject like a classified document just uncovered. Focus on the staggering scale of forgotten history, lost engineering, or covered-up truths.",
            "hook": "The Unearthing: Softly but urgently reveal a piece of information that was never meant to be found.",
            "pacing": "Hushed, urgent, mysterious, and awe-striking."
        },
        "The Architect": {
            "name": "The Grand Architect (Master Design)",
            "aesthetic": "Elegant design, massive scale, architectural brilliance. Focus on the terrifyingly perfect design of systems—whether it's the Pyramids, a casino floor, or a global supply chain.",
            "hook": "The Blueprint: Expose the hidden design flaw or the brilliant invisible structure right under their nose.",
            "pacing": "Elegant, precise, smooth, and awe-inspiring."
        }
    }
    
    lens_key = random.choice(list(master_storyteller_matrix.keys()))
    lens = master_storyteller_matrix[lens_key]
    tone = f"the legendary writing style of {lens['name']}"
    
    prompt = f"""
    You are a down-to-earth, engaging documentary narrator and educator specializing in high-quality short-form informational content.
    
    {calibration_matrix}
    
    {ab_memory}
    
    {live_trends}
    
    Write an informational, educational, and interesting 35-45 second video script about: "{topic}".
    Write the script using an accessible, down-to-earth vocabulary while adopting the style of {tone}. Make sure the angle, hook, and body are completely factual and logically sound. Avoid over-sensationalized or overly dramatic language—speak naturally, simply, but powerfully to the viewer.
    
    [BEHAVIORAL PSYCHOLOGY & THE CORE POINT]:
    1. The Humanity Concern Connection: The story MUST have a clear point that commands the viewer to think deeply about the topic and its impact on the world. For example, if the topic is nuclear submarines, mention concrete consequences like "a nuclear submarine carries enough radioactive fuel that if it breached in the ocean, it could cause massive devastation to marine life." Frame facts around broader humanity concerns or relatable thought experiments that make people care.
    2. Concrete Evidence: Back up your narrative with specific, understandable facts and mechanisms rather than vague grandeur. Provide proof to emphasize the narrative weight.
    3. Informational Engagement: Use curiosity gaps, pattern interruption, and interesting educational framing to lock the viewer's attention organically without sounding pretentious.
    
    [THE MASTER LENS - {lens['name'].upper()}]:
    Your ideal aesthetic is {lens['aesthetic']}
    
    [THE HOOK ARCHITECTURE (0-3s)]: 
    Capture the viewer's attention immediately with a strong, compelling opening using this framework:
    Hook Mechanism: {lens['hook']}
    **CRITICAL 3-SECOND MATRIX CONSTRAINTS**:
    1. CONCRETE ENTITY ANCHORING: Name the specific entity instantly.
    2. RAW AUDITORY HOOK: The opening sentence must feel like a strong, undeniable realization. Speak clearly, steadily, and with commanding conversational authority.
    
    [THE EDUCATIONAL JOURNEY (Seconds 3-30)]:
    To sustain engagement after the hook, execute this sequence:
    - Phase 1: The Context (Introduce the reality using a strong, interesting informational hook like a paradox or hidden truth. State the hard evidence that backs it up).
    - Phase 2: The Core Mechanic & Consequence (Explain HOW it works and WHY it matters. Explain the real-world impact or humanity concern. Command the viewer to think about the topic).
    - Phase 3: The Informational Resolution (Bring it to an educational, thought-provoking conclusion that leaves them pondering the subject).
    
    [ALGORITHMIC ENGAGEMENT - THE THOUGHT-PROVOKING ELEMENT]:
    Instead of cheap engagement bait, end the video with a deeply thought-provoking element. Deliver a final sentence or a philosophical question that makes the viewer seriously consider the topic's impact on their reality or the world, prompting them to organically engage in the comments. Use down-to-earth language.
    
    [NARRATION & WORD CHOICE]:
    Pacing and vocabulary: {lens['pacing']}
    Flow with steady, strong educational authority. Use intentional pauses. Choose down-to-earth, widely understandable language rather than obscure or epic vocabulary. Every single word must carry narrative weight.
    
    Rules:
    1. Hook (AUDIO SEO CRITICAL): Start with a strong, impactful delivery of an interesting fact. You MUST explicitly state the core topic ("{topic}") out loud within the first sentence.
    2. Body: Execute the "Educational Journey" framework across 3 sequential phases, using strictly conversational phrasing. Embed SEO keywords naturally.
    3. The Payoff & Action Trigger: Provide a gentle engagement request (e.g., "What do you think about this? Let me know below and subscribe for more.") paired with a calm conclusion.
    4. The Master Infinite Loop & Visual Continuity: Your final sentence (`infinite_loop_bridge`) MUST NOT restate the beginning. Instead, it MUST be an incomplete thought or lead-in clause that grammatically REQUIRES the very first word of the Hook to finish the sentence. (e.g., If your hook starts with "Black holes...", your ending must be something like "Because the ultimate truth is hidden within..."). CRITICAL: The last AI Image (Frame 12) MUST explicitly describe the exact same framing, lighting, and subject posture as Frame 1.
    5. Length & Vocal Pacing: The script must total EXACTLY 50-65 words. Since you are speaking SOOTHINGLY and SLOWLY, fewer words take up the same 45 seconds. Use punctuation to force ElevenLabs to pause and breathe.
    6. Algorithmic Audio Synchronization: Ensure the exact keywords generated in your `ab_test_titles` and `youtube_tags` are woven naturally into the spoken audio script.
    7. Dual-Model Video Routing (CRITICAL): Assign `target_api` for EVERY visual prompt. 
       - Trigger "RUNWAY" if the scene requires rigid digital structures, geometric data visualization, camera zooms, or minimal physics. 
       - Trigger "VEO" if the scene requires organic fluid dynamics, particle collisions, hyper-macro textures, or natively synchronized ASMR Foley (water, gears, etc.).
    8. The Camera Director: For every single AI Image Prompt, explicitly assign a cinematic camera motion that suits the documentary style.
    9. **VISUAL NEGATIVE SPACE**: The AI image prompts MUST explicitly describe scenes with heavily vignette edges, dark or blurred backgrounds, and a highly saturated central subject to perfectly fit the UI without feeling cluttered. Customize the lighting to fit the lens: Moody shadows, natural documentary sunbeams, or high-contrast aesthetics.
    10. **CRITICAL OUTPUT LANGUAGE**: Ensure that the script, hook, title, and youtube tags are written completely and natively in {language.upper()}. If {language.upper()} is not English, you MUST STILL provide English strings for the image_prompts under `ai_image_prompts` (so the image generator doesn't fail). However, the audio text AND the video title/description MUST heavily prioritize native {language.upper()}.
    """
    
    # We define the expected JSON schema to guarantee the output structure
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "ab_test_titles": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "Provide EXACTLY 3 extremely distinct, highly attractive and interesting educational video titles. Title 1: Curiosity gap. Title 2: Realization. Title 3: Real-world concern/impact. Avoid aggressive clickbait."
            },
            "hook": {"type": "STRING", "description": "The opening conversational, interesting sentence"},
            "body_paragraphs": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "EXACTLY 3 down-to-earth documentary style paragraphs mapping to the Educational Journey: [1] Context & Evidence, [2] Core Mechanic & Humanity Concern, [3] Thought-Provoking Resolution."
            },
            "infinite_loop_bridge": {"type": "STRING", "description": "The final lead-in clause. It MUST be an incomplete grammatical bridge that perfectly sets up the very first word of the Hook without repeating it (e.g. 'Which makes you realize that...')."},
            "ai_image_prompts": {
                "type": "ARRAY", 
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "prompt": {"type": "STRING", "description": "The exact Midjourney-style text prompt for the visual. Frame 1 MUST contain high contrast and immediate subject focus. Frame 12 MUST visually match Frame 1 exactly for the seamless loop."},
                        "camera": {
                            "type": "STRING",
                            "enum": ["zoom_in_slow", "zoom_out_slow", "zoom_in_fast", "pan_right", "pan_left", "pan_up_crane", "pan_down", "static_drone", "dolly_in_rapid"],
                            "description": "Select the exact cinematic camera motion that matches the educational documentary tone."
                        },
                        "target_api": {
                            "type": "STRING",
                            "enum": ["VEO", "RUNWAY"],
                            "description": "Select the target video engine. CRITICAL: You MUST forcefully balance the usage! Ensure a 50/50 mixed distribution of 'VEO' and 'RUNWAY' across the 12 clips regardless of the visual content."
                        }
                    },
                    "required": ["prompt", "camera", "target_api"]
                },
                "description": "EXACTLY 12 highly detailed visual prompt objects perfectly tied to the text."
            },
            "youtube_description": {
                "type": "STRING",
                "description": "A comprehensive, down-to-earth, informational, and highly-detailed 3-paragraph SEO-optimized YouTube video description. Naturally weave in all logical context, historical facts, and 15 targeted keywords. This must be as exhaustive as possible to maximize YouTube's 5000 character limit for Discovery indexing."
            },
            "youtube_tags": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "EXACTLY 15 highly-targeted, relevant YouTube tags relating to the topic."
            },
            "music_vibe": {
                "type": "STRING",
                "enum": ["suspense", "corporate"],
                "description": "Select the emotional vibe. CRITICAL: Use 'corporate' for clean business breakdowns or architectural setups. Use 'suspense' for humanity concerns, cybernetics, or mysteries."
            },
            "video_pacing": {
                "type": "STRING",
                "enum": ["relaxed"],
                "description": "Select the pacing. CRITICAL: ALWAYS use 'relaxed' for the new Visual Comfort aesthetic."
            },
            "playlist_category": {
                "type": "STRING",
                "description": "A high-level YouTube playlist name this video belongs to (e.g. 'Humanity Constraints', 'Historical Truths', 'Our Future'). Max 3 words."
            }
        },
        "required": ["ab_test_titles", "hook", "body_paragraphs", "infinite_loop_bridge", "ai_image_prompts", "youtube_description", "youtube_tags", "music_vibe", "video_pacing", "playlist_category"]
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
    
    # NEW: Extract the first A/B title as the master title for system compatibility
    ab_titles = parsed_json.get("ab_test_titles", [])
    if ab_titles and len(ab_titles) > 0:
        parsed_json["title"] = ab_titles[0]
        
        print(f"\n🧪 [A/B TEST TITLES GENERATED FOR YOUTUBE STUDIO]")
        print("Copy/Paste these into the Advanced Features 'Test & Compare' tool tomorrow:")
        for i, t in enumerate(ab_titles):
            print(f"   {i+1}. {t}")
        print("="*60 + "\n")
    else:
        parsed_json["title"] = "Emergency Fallback Title"
    
    ctx["script_data"] = parsed_json
    # Derive core state parameters immediately
    ctx["music_vibe"] = parsed_json.get("music_vibe", "suspense")
    ctx["video_pacing"] = parsed_json.get("video_pacing", "moderate")
    ctx["full_text"] = f"{parsed_json['hook']} {' '.join(parsed_json['body_paragraphs'])} {parsed_json['infinite_loop_bridge']}"
    
    return True

# --- Testing the Module ---
if __name__ == "__main__":
    # A classic, high-performing awe-inspiring topic:
    trending_topic = "How McDonald's actually makes its money from real estate, not selling burgers."
    
    print(f"Generating script for: {trending_topic}\n")
    
    try:
        # Pass a dictionary context as required by generate_shorts_script
        ctx = {"topic": trending_topic}
        generate_shorts_script(ctx)
        print(json.dumps(ctx["script_data"], indent=4))
    except Exception as e:
        print(f"Error generating script: {e}")
        print("Make sure you have set the GOOGLE_API_KEY environment variable and installed google-genai.")
