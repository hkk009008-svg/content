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
    
    Write a sweeping, profoundly emotional, 1-2 minute cinematic short film script exploring the deepest human meaning of: "{topic}".
    Write the script using an accessible, down-to-earth vocabulary while adopting the style of an A24 art-house film. The entire goal is to leave the viewer feeling: "Yes... I know that exact feeling too. I have experienced it."
    
    [PROFOUND HUMAN CONNECTION & THE CORE EMOTION]:
    1. The Relatable Truth: The story MUST explore the meaning of life, love, family, and the profound beauty of ordinary things. Leave the viewer with the profound feeling of: "Yes... I know that exact feeling too. I have experienced it." That emotional resonance is the absolute Master Goal.
    2. Tension & Tranquility: Your script must ride an emotional rollercoaster into the director's mind. Alternate between immersive, intense tension and beautiful, breathtaking tranquility. Make it deeply human.
    3. The Mirror: Make the viewer see themselves in the narrative.
    
    [THE MASTER LENS - {lens['name'].upper()}]:
    Your ideal aesthetic is {lens['aesthetic']}
    
    [THE CINEMATIC SHORT FILM (1-2 minutes)]:
    You are writing a sweeping, cinematic A24-style art-house short film. There are no algorithmic constraints. 
    1. THE ARCHITECTURE: The script must unfold poetically. It must take its time, breathe, and build immense atmospheric and emotional weight.
    2. THE MOOD: Speak clearly, steadily, and with profound vulnerability and deep emotion. 
    3. THE PACING: {lens['pacing']} Use down-to-earth language. Every single word must carry deep narrative weight. The total script must be roughly 150-200 words to span a visually complex 2-minute timeline.
    
    [EMOTIONAL IMMERSION]:
    End the film with a deeply thought-provoking, existential, or poetic question that makes the viewer seriously consider their own humanity, prompting them to organically sit in silence and reflect on their existence.
    
    Rules:
    1. Hook: Start with a deeply atmospheric, poetic opening observation about ordinary life or the human condition.
    2. Body: Expand the cinematic journey, diving into psychological exploration, love, nostalgia, tension, and tranquility.
    3. The Payoff: Bring the narrative to a stunning, poetic, and philosophical conclusion. NO engagement bait.
    4. FOLEY & SOUND: For every single visual frame, you must strictly imagine the environmental sound. You will provide a `scene_foley` instruction for the Audio Mixer to generate the precise sound effects (wind, rain, silence, footsteps) to lay underneath the actor's voice over that specific image!
    5. The Camera Psychology Director: You must strictly adhere to the `Cinematography Rules` defined in the Master Director's Blueprint above. 
    6. Dynamic Visual Effects: For every prompt, explicitly inject the `Color Grading & Aesthetic` from the Director's Blueprint into your visual setup to guarantee exact color mapping.
    7. **HERO SUBJECT CONTINUITY**: You MUST use the exact `The Master Hero Subject` defined in the Blueprint as the core anchor for every single shot. Frame 1 MUST be an 'Extreme Close-Up (ECU)' of this Hero Subject. Every single of the 20 image prompts MUST explicitly feature this same Hero Subject. Describe different cinematic spatial angles (low angle, wide shot, high angle) to keep it dynamic.
    8. **VISUAL PSYCHOLOGY**: Every visual MUST leverage the Rule of Thirds and heavy NEGATIVE SPACE for an ultra-premium widescreen aesthetic.
    9. **CRITICAL OUTPUT LANGUAGE**: Ensure that the script is written completely and natively in {language.upper()}.
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
                            "prompt": {"type": "string", "description": "The visual prompt. CRITICAL: You MUST include the exact `Color Grading & Aesthetic` commands and ensure the exact same `The Master Hero Subject` is in all 20 frames to ensure visual continuity. Frame 1 MUST be an 'Extreme Close-Up (ECU)' of the Hero Subject. Use varying cinematic spatial angles (low angle, wide shot, high angle). All frames MUST explicitly use 'Rule of Thirds' and heavy NEGATIVE SPACE. Frame 20 MUST visually match Frame 1 exactly."},
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
                                "description": "Select the target video engine. CRITICAL: You MUST forcefully balance the usage! Ensure an equal mixed distribution of 'VEO', 'RUNWAY', and 'LUMA' across the 20 clips to bypass API rate-limits."
                            },
                            "scene_foley": {
                                "type": "string",
                                "description": "Crucial for audio immersion. Describe the raw environmental Foley Sound FX for this scene. Examples: 'Heavy rain pouring on concrete', 'Hollow wind blowing through empty room', 'Children laughing softly in the distance', 'Mechanical clock ticking'."
                            }
                        },
                        "required": ["prompt", "camera", "visual_effect", "target_api", "scene_foley"]
                    },
                    "description": "EXACTLY 20 highly detailed visual prompt objects perfectly tied to the text."
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
        # Call the absolute bleeding-edge Claude 4.6 Opus model forcing structured output
        response = client.messages.create(
            model="claude-opus-4-6",
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
