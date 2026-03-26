import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

# Initialize the Anthropic client 
# (Requires ANTHROPIC_API_KEY environment variable to be set)
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def generate_shorts_script(ctx: dict) -> bool:
    """
    Generates a highly-engaging 60-second YouTube Shorts script directly into the OmniContext.
    Enforces a strict JSON response via Claude 3.5 Sonnet's "Tool Use" functionality.
    """
    topic = ctx["topic"]
    language = ctx.get("language", "English")
    print(f"\n✍️ [PHASE A] Writing highly-retentive script via Claude 3.5 Sonnet in {language.upper()} for topic: {topic}")
    import random
    from phase_e_learning import get_top_performing_context, fetch_live_youtube_trends
    ab_memory = get_top_performing_context()
    live_trends = fetch_live_youtube_trends()
    
    blueprint = ctx.get("production_blueprint", {})
    blueprint_str = ""
    if blueprint:
        blueprint_str = f"""
        [MASTER DIRECTOR'S PRODUCTION BLUEPRINT]
        Read and OBEY these absolute constraints set by the Chief Director:
        - Director's Narrative Vision: {blueprint.get('director_vision', 'None')}
        - Cinematography Rules: {blueprint.get('cinematography_rules', 'None')}
        - Color Grading & Aesthetic: {blueprint.get('color_grading_palette', 'None')}
        - Sound Design & Music: {blueprint.get('sound_design_and_music', 'None')}
        - The Master Hero Subject: {blueprint.get('hero_subject', 'A mysterious object')}
        """
    
    calibration_matrix = ""
    if os.path.exists("CALIBRATION_MATRIX.txt"):
        with open("CALIBRATION_MATRIX.txt", "r") as f:
            raw_matrix = f.read()
            calibration_matrix = f"\n[🔥 THE OMNI-CALIBRATION MATRIX 🔥]\n{raw_matrix}\n"
    
    master_storyteller_matrix = {
        "The Strategist": {
            "name": "The Master Strategist (Systems & Leverage)",
            "aesthetic": "Cold, calculated, and terrifyingly precise. Emphasize the hidden mechanisms behind massive systems. Break down business models, historical mysteries, or tech like a mastermind solving a global puzzle.",
            "hook": "The Paradigm Shatter: Instantly tell the viewer a core truth they believe is actually a carefully constructed lie.",
            "pacing": "Methodical, sharp, authoritative, and brilliantly analytical."
        },
        "The Machiavellian": {
            "name": "The Machiavellian Operator (Power & Strategy)",
            "aesthetic": "Ruthless efficiency, leverage, and global power plays. Focus on the psychology of manipulation, brilliant marketing, and how empires—corporate or historical—control the masses.",
            "hook": "The Illusion of Control: Dramatically reveal that their choices or beliefs are actually perfectly designed by a hidden system.",
            "pacing": "Calculated, dominant, slightly sinister, and unbroken."
        },
        "The Cyber-Architect": {
            "name": "The Cyber-Architect (Futuristic Inevitability)",
            "aesthetic": "Neon, data-driven, and slightly dystopian. Treat the subject as an inevitable mathematical future. Focus on terrifyingly beautiful cybernetics, global networks, and unstoppable technological shifts.",
            "hook": "The Uncomfortable Inevitability: A heavy realization that a monumental, slightly terrifying shift has already occurred while they were distracted.",
            "pacing": "Sleek, rapid, electric, and unstoppable."
        },
        "The Insider": {
            "name": "The Insider (Forbidden Mechanics)",
            "aesthetic": "Secretive, forbidden knowledge. Treat the subject like a classified business or engineering document just uncovered. Focus on the staggering scale of forgotten history, lost engineering, or covered-up truths.",
            "hook": "The Warning: Urgently reveal a piece of information or a mechanism that the world fundamentally misunderstands and doesn't want them to know.",
            "pacing": "Hushed, urgent, mysterious, and awe-striking."
        },
        "The Builder": {
            "name": "The Grand Builder (Master Engineering)",
            "aesthetic": "Elegant design, massive scale, brutalist architectural brilliance. Focus on the terrifyingly perfect design of systems—whether it's the Pyramids, a casino floor, or a global supply chain.",
            "hook": "The Blindspot: Expose the beautiful, calculated, and ruthless invisible structure right under their nose that dictates their reality.",
            "pacing": "Elegant, precise, smooth, and awe-inspiring."
        }
    }
    
    lens_key = random.choice(list(master_storyteller_matrix.keys()))
    lens = master_storyteller_matrix[lens_key]
    tone = f"the legendary writing style of {lens['name']}"
    
    system_prompt = f"""
    You are a highly-skilled but subordinate scriptwriter and cinematography assistant. You MUST strictly follow the attached Master Director's Production Blueprint to create high-quality short-form visual content.
    
    {calibration_matrix}
    
    {ab_memory}
    
    {live_trends}
    
    {blueprint_str}
    
    Write an informational, educational, and interesting 35-45 second video script about: "{topic}".
    Write the script using an accessible, down-to-earth vocabulary while adopting the style of {tone}. Make sure the angle, hook, and body are completely factual and logically sound. Avoid over-sensationalized or overly dramatic language—speak naturally, simply, but powerfully to the viewer.
    
    [REVERSE PSYCHOLOGY & THE CORE POINT]:
    1. The Paradigm Flip (Reverse Psychology): The story MUST aggressively challenge the viewer's core assumptions. Tell them they are currently being played, that the system is rigged against their understanding, or that a "forbidden" mechanism is operating right in front of them. Make the truth feel like an uncomfortable secret they aren't supposed to know.
    2. Concrete Evidence of Power: Back up your narrative with specific, undeniable facts, money metrics, or engineering mechanics rather than vague grandeur. Provide proof of the leverage and power scale.
    3. The Cognitive Dissonance: Use deep curiosity gaps and pattern interruption to lock their attention organically. Make the viewer feel like they must watch to the end to un-learn a lie they've been taught.
    
    [THE MASTER LENS - {lens['name'].upper()}]:
    Your ideal aesthetic is {lens['aesthetic']}
    
    [THE HOOK ARCHITECTURE (0-2s)] (SHORTS BINARY GATE OPTIMIZATION): 
    Capture the viewer's attention immediately with a hyper-aggressive, paradigm-breaking opening using this framework to force the Swipe-Away Rate below 15%:
    Hook Mechanism: {lens['hook']}
    **CRITICAL 2-SECOND MATRIX CONSTRAINTS**:
    1. THE REVERSE PSYCHOLOGY ANCHOR: The hook MUST instantly tell the viewer what they *think* is true, and violently shatter it. Your goal is to secure the 2-Second Hook metric to boost completion probability by 60%.
    2. CONCRETE ENTITY ANCHORING: Name the specific entity instantly.
    3. RAW AUDITORY HOOK: Speak clearly, steadily, and with absolute, almost dangerous, conversational authority.
    
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
    CRITICAL AUDIO SEO: Ensure that the spoken script naturally contains the exact high-RPM keywords that will be placed in the title and description, as the platform's auto-captioning systems now index audio vectors directly.
    
    Rules:
    1. Hook (AUDIO SEO CRITICAL): Start with a strong, impactful delivery of an interesting fact. You MUST explicitly state the core topic ("{topic}") out loud within the first sentence.
    2. Body: Execute the "Educational Journey" framework across 3 sequential phases, using strictly conversational phrasing.
    3. The Payoff & Action Trigger: Provide a gentle engagement request (e.g., "What do you think about this? Let me know below and subscribe for more.") paired with a calm conclusion.
    4. The Master Infinite Loop & Visual Continuity: Your final sentence (`infinite_loop_bridge`) MUST NOT restate the beginning. Instead, it MUST be an incomplete thought or lead-in clause that grammatically REQUIRES the very first word of the Hook to finish the sentence. (e.g., If your hook starts with "Black holes...", your ending must be something like "Because the ultimate truth is hidden within..."). CRITICAL: The last AI Image (Frame 12) MUST explicitly describe the exact same framing, lighting, and subject posture as Frame 1.
    5. Length & Vocal Pacing: The script must total EXACTLY 50-65 words. Since you are speaking SOOTHINGLY and SLOWLY, fewer words take up the same 45 seconds. Use punctuation to force ElevenLabs to pause and breathe.
    6. High-CPM Algorithmic Synchronization: Ensure the exact keywords generated in your `ab_test_titles` and `youtube_tags` are wove naturally into the spoken audio script. You must actively target High-CPM AdSense keyword structures (Finance, Strategy, Enterprise Tech, Economics) even if the topic is historical or scientific.
    8. The Camera Psychology Director: You must strictly adhere to the `Cinematography Rules` defined in the Master Director's Blueprint above. 
    9. Dynamic Visual Effects: For every prompt, explicitly inject the `Color Grading & Aesthetic` from the Director's Blueprint into your visual setup to guarantee exact color mapping.
    10. **HERO SUBJECT CONTINUITY**: You MUST use the exact `The Master Hero Subject` defined in the Blueprint as the core anchor for every single shot. Frame 1 MUST be an 'Extreme Close-Up (ECU)' of this Hero Subject. Every single of the 12 image prompts MUST explicitly feature this same Hero Subject. Describe different cinematic spatial angles (low angle, wide shot, high angle) to keep it dynamic.
    11. **VISUAL PSYCHOLOGY & HIGH COMBUSTION AESTHETIC**: Every visual MUST leverage the Rule of Thirds and heavy NEGATIVE SPACE. Frame 1 (The Hook) MUST explicitly be an EXTREME CLOSE-UP (ECU) of the Hero Subject to instantly capture biological focus.
    12. **CRITICAL OUTPUT LANGUAGE**: Ensure that the script, hook, title, and youtube tags are written completely and natively in {language.upper()}.
    """
    
    # We define the expected JSON schema aggressively formatted for Anthropic Tool Use
    tool_schema = {
        "name": "generate_script",
        "description": "Outputs the final orchestrated script following the required JSON schema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ab_test_titles": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "description": "Provide EXACTLY 3 extremely distinct, highly attractive educational video titles. The primary keyword MUST appear within the first 40 characters. Use Power Words like 'Ultimate', 'Proven', or 'Surprising'. Title 1: Curiosity gap. Title 2: Realization. Title 3: Real-world concern/impact."
                },
                "hook": {"type": "string", "description": "The opening conversational, interesting sentence"},
                "body_paragraphs": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "description": "EXACTLY 3 down-to-earth documentary style paragraphs mapping to the Educational Journey: [1] Context & Evidence, [2] Core Mechanic & Humanity Concern, [3] Thought-Provoking Resolution."
                },
                "infinite_loop_bridge": {"type": "string", "description": "The final lead-in clause. It MUST be an incomplete grammatical bridge that perfectly sets up the very first word of the Hook without repeating it (e.g. 'Which makes you realize that...')."},
                "ai_image_prompts": {
                    "type": "array", 
                    "items": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "The visual prompt. CRITICAL: You MUST include the exact `Color Grading & Aesthetic` commands and ensure the exact same `The Master Hero Subject` is in all 12 frames to ensure visual continuity. Frame 1 MUST be an 'Extreme Close-Up (ECU)' of the Hero Subject. Use varying cinematic spatial angles (low angle, wide shot, high angle). All frames MUST explicitly use 'Rule of Thirds' and heavy NEGATIVE SPACE. Frame 12 MUST visually match Frame 1 exactly."},
                            "camera": {
                                "type": "string",
                                "enum": ["zoom_in_slow", "zoom_out_slow", "zoom_in_fast", "pan_right", "pan_left", "pan_up_crane", "pan_down", "static_drone", "dolly_in_rapid"],
                                "description": "Select the exact cinematic camera motion. CRITICAL: You MUST execute the exact `Cinematography Rules` specified in the Director's Blueprint."
                            },
                            "visual_effect": {
                                "type": "string",
                                "enum": ["gritty_contrast", "cinematic_glow", "cyberpunk_glitch", "dreamy_blur", "documentary_neutral"],
                                "description": "Select an FFMPEG post-production aesthetic filter that perfectly matches the narrative emotion of this specific clip."
                            },
                            "target_api": {
                                "type": "string",
                                "enum": ["VEO", "RUNWAY", "LUMA"],
                                "description": "Select the target video engine. CRITICAL: You MUST forcefully balance the usage! Ensure an equal mixed distribution of 'VEO', 'RUNWAY', and 'LUMA' across the 12 clips to bypass API rate-limits."
                            }
                        },
                        "required": ["prompt", "camera", "visual_effect", "target_api"]
                    },
                    "description": "EXACTLY 12 highly detailed visual prompt objects perfectly tied to the text."
                },
                "youtube_description": {
                    "type": "string",
                    "description": "A comprehensive, SEO-optimized YouTube video description. CRITICAL: The first 3 lines MUST contain a clear value proposition for LLM parsing. Naturally weave in massive historical context and heavily prioritize high-RPM/high-CPM business, tech, or strategy financial keywords. This must be exhaustive but prioritize the top 3 lines."
                },
                "youtube_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "EXACTLY 15 highly-targeted YouTube tags. Focus on lucrative algorithmic search terms that target the 25-35 male demographic (e.g., Business Strategy, Tech Leverage, Global Economics, Automation, Success Patterns)."
                },
                "music_vibe": {
                    "type": "string",
                    "enum": ["suspense", "corporate", "gritty", "cyberpunk"],
                    "description": "Select the emotional vibe. CRITICAL: Use 'corporate' for clean business/financial breakdowns, 'gritty' for survival/mechanical power, 'cyberpunk' for AI/futurism, and 'suspense' for hidden psychological mysteries."
                },
                "video_pacing": {
                    "type": "string",
                    "enum": ["calculated"],
                    "description": "Select the pacing. CRITICAL: ALWAYS use 'calculated' for this strategic aesthetic."
                },
                "playlist_category": {
                    "type": "string",
                    "description": "A high-level YouTube playlist name this video belongs to (e.g. 'Humanity Constraints', 'Historical Truths', 'Our Future'). Max 3 words."
                }
            },
            "required": ["ab_test_titles", "hook", "body_paragraphs", "infinite_loop_bridge", "ai_image_prompts", "youtube_description", "youtube_tags", "music_vibe", "video_pacing", "playlist_category"]
        }
    }
    
    try:
        # Call the Claude 3.5 Sonnet model forcing structured output
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=3000,
            system=system_prompt,
            messages=[
                {"role": "user", "content": "Generate the masterpiece script using the `generate_script` tool."}
            ],
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": "generate_script"}
        )
        
        # Extract the tool use payload generated by Claude
        tool_call = next((block for block in response.content if block.type == "tool_use"), None)
        if not tool_call:
            raise Exception("Claude did not return the tool call payload as requested.")
            
        parsed_json = tool_call.input
        
        # Inject the randomly selected tone for the experiment logger
        parsed_json['tone_used'] = tone
        
        # Extract the first A/B title as the master title for system compatibility
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
    except Exception as e:
        print(f"❌ Error generating script via Claude 3.5 Sonnet: {e}")
        return False

# --- Testing the Module ---
if __name__ == "__main__":
    # A classic, high-performing awe-inspiring topic:
    trending_topic = "How McDonald's actually makes its money from real estate, not selling burgers."
    
    print(f"Generating script for: {trending_topic}\n")
    
    try:
        ctx = {"topic": trending_topic}
        generate_shorts_script(ctx)
        print(json.dumps(ctx["script_data"], indent=4))
    except Exception as e:
        print(f"Error generating script: {e}")
