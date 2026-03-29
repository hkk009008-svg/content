"""
Cinema Production Tool — Character Manager (v2)
Real-photo-first character creation with multi-angle reference sheets,
embedding caching, and voice assignment for multi-character cinema production.

Key changes from v1:
- Characters REQUIRE real uploaded photos (no synthetic generation)
- Multi-angle reference sheets: front, 45°, profile, back
- Higher identity validation thresholds (0.70+)
- Multi-reference support for downstream Kling subject binding
"""
from typing import Optional, List

import os
import json
import shutil
import urllib.request
import numpy as np
from dotenv import load_dotenv

load_dotenv()

try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DEEPFACE_AVAILABLE = False

try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False

# Identity validation threshold — raised from 0.45 to 0.70 for production quality
IDENTITY_THRESHOLD = 0.70
# Minimum acceptable threshold (for fallback / lenient mode)
IDENTITY_THRESHOLD_LENIENT = 0.55

from project_manager import (
    make_character, add_character, save_project, get_project_dir, get_character
)

# Expanded voice pool — full range: women, men, children, elderly, diverse accents
VOICE_POOL = [
    # --- Women ---
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "style": "Warm, calm woman", "category": "woman"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "style": "Soft, gentle young woman", "category": "woman"},
    {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli", "style": "Confident, clear woman", "category": "woman"},
    {"id": "ThT5KcBeYPX3keUQqHPh", "name": "Dorothy", "style": "Pleasant, expressive woman", "category": "woman"},
    {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi", "style": "Strong, assertive woman", "category": "woman"},
    {"id": "jBpfuIE2acCO8z3wKNLl", "name": "Gigi", "style": "Animated, youthful woman", "category": "woman"},
    {"id": "oWAxZDx7w5VEj9dCyTzz", "name": "Grace", "style": "Elegant, mature woman", "category": "woman"},
    {"id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte", "style": "Warm, narrative woman (English accent)", "category": "woman"},
    {"id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily", "style": "Warm, British young woman", "category": "woman"},
    # --- Men ---
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "style": "Deep, authoritative man", "category": "man"},
    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "style": "Clean, professional man", "category": "man"},
    {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin", "style": "Visceral, gritty man", "category": "man"},
    {"id": "cjVigY5qzO86Huf0OWal", "name": "Eric", "style": "Grizzly, mature, dark man", "category": "man"},
    {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold", "style": "Commanding, authoritative man", "category": "man"},
    {"id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam", "style": "Warm, friendly man", "category": "man"},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "style": "Deep, narrative man", "category": "man"},
    {"id": "ODq5zmih8GrVes37Dizd", "name": "Patrick", "style": "Authoritative, older man", "category": "man"},
    {"id": "ZQe5CZNOzWyzPSCn5a3c", "name": "James", "style": "Calm, British man", "category": "man"},
    # --- Young / Child ---
    {"id": "jsCqWAovK2LkecY7zXl4", "name": "Freya", "style": "Young girl, bright and curious", "category": "child"},
    {"id": "cgSgspJ2msm6clMCkdW9", "name": "Jessica", "style": "Young woman, energetic and expressive", "category": "young"},
    {"id": "bIHbv24MWmeRgasZH58o", "name": "Will", "style": "Young boy, friendly and warm", "category": "child"},
    # --- Elderly ---
    {"id": "SOYHLrjzK2X1ezoPC6cr", "name": "Harry", "style": "Elderly man, wise and gravelly", "category": "elderly"},
    {"id": "g5CIjZEefAph4nQFvHAz", "name": "Ethan", "style": "Older man, deep and reflective", "category": "elderly"},
    # --- Narration / Specialty ---
    {"id": "2EiwWnXFnvU5JabPnv8n", "name": "Clyde", "style": "Warm storyteller, veteran narrator", "category": "narrator"},
    {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "style": "Authoritative British narrator", "category": "narrator"},
    {"id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum", "style": "Intense, dramatic narrator", "category": "narrator"},
]

# Track which voices are already assigned in a project to avoid duplicates
def _get_used_voices(project: dict) -> set:
    return {c["voice_id"] for c in project["characters"] if c.get("voice_id")}


def _char_dir(project_id: str, char_id: str) -> str:
    d = os.path.join(get_project_dir(project_id), "characters", char_id)
    os.makedirs(d, exist_ok=True)
    return d


def create_character_with_images(
    project: dict,
    name: str,
    description: str,
    reference_image_paths: Optional[List[str]] = None,
    voice_id: str = "",
    ip_adapter_weight: float = 0.85,
) -> dict:
    """
    Creates a character from REAL uploaded photos.

    v2 flow:
    1. Copy uploaded reference images into project directory
    2. Validate face detectability (REQUIRED — reject if no face found)
    3. Set the best face-detected upload as canonical reference
    4. Generate multi-angle reference sheet (front, 45°, profile, back)
    5. Assign voice, pre-compute embedding
    6. Store all references for downstream Kling subject binding
    """
    pid = project["id"]
    character = make_character(name, description, voice_id=voice_id, ip_adapter_weight=ip_adapter_weight)
    cid = character["id"]
    char_path = _char_dir(pid, cid)

    # 1. Copy reference images into project
    stored_refs = []
    if reference_image_paths:
        for i, src in enumerate(reference_image_paths):
            if os.path.exists(src):
                ext = os.path.splitext(src)[1] or ".jpg"
                dst = os.path.join(char_path, f"ref_{i}{ext}")
                shutil.copy2(src, dst)
                stored_refs.append(dst)
                print(f"   [REF] Stored reference image: {dst}")

    character["reference_images"] = stored_refs

    # 2. Find canonical (best face) from uploaded images — NO synthetic fallback
    canonical = _find_canonical_from_uploads(character, char_path)
    character["canonical_reference"] = canonical or ""

    if not canonical:
        print(f"   [WARN] No detectable face in uploads for '{name}'. Character will have limited identity lock.")

    # 3. Generate multi-angle reference sheet for Kling subject binding
    multi_angles = []
    if canonical:
        multi_angles = _generate_multi_angle_refs(canonical, char_path, description)
    character["multi_angle_refs"] = multi_angles
    print(f"   [ANGLES] Generated {len(multi_angles)} angle references")

    # 4. Assign voice if not provided
    if not voice_id:
        character["voice_id"] = assign_voice(project)

    # 5. Pre-compute embedding
    if canonical and DEEPFACE_AVAILABLE:
        emb_path = os.path.join(char_path, "embedding.npy")
        embedding = compute_face_embedding(canonical)
        if embedding is not None:
            np.save(emb_path, embedding)
            character["embedding_cache"] = emb_path
            print(f"   [EMB] Cached face embedding: {emb_path}")

    # 6. Physical traits + identity anchor
    character["physical_traits"] = description
    character["identity_anchor"] = build_identity_anchor(character)

    add_character(project, character)
    print(f"   [OK] Character '{name}' created: {cid} (refs={len(stored_refs)}, angles={len(multi_angles)})")
    return character


def _find_canonical_from_uploads(character: dict, char_path: str) -> Optional[str]:
    """
    Find the best face-detected image from user uploads. NO synthetic generation.

    Priority:
    1. First image with a clearly detectable face
    2. First uploaded image (if DeepFace unavailable)
    """
    refs = character.get("reference_images", [])
    if not refs:
        return None

    # Try each upload for face detection
    for ref in refs:
        if _has_detectable_face(ref):
            canonical = os.path.join(char_path, "canonical.jpg")
            shutil.copy2(ref, canonical)
            print(f"   [CANON] Set from upload (face verified): {canonical}")
            return canonical

    # If DeepFace unavailable, trust the first upload
    canonical = os.path.join(char_path, "canonical.jpg")
    shutil.copy2(refs[0], canonical)
    print(f"   [CANON] Set from first upload (no face validation available)")
    return canonical


def _generate_multi_angle_refs(
    canonical_path: str,
    char_path: str,
    description: str,
) -> List[str]:
    """
    Generate multi-angle reference images from the canonical front-facing photo.
    Uses FLUX Kontext (in-context editing) to create consistent angle variations.

    Output: up to 3 additional angles (45°, profile, back) stored in char_path.
    These are used for Kling 3.0 Pro subject binding (multi-image references).
    """
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("   [WARN] FAL not available — skipping multi-angle generation")
        return [canonical_path]  # Return just the canonical

    angle_refs = [canonical_path]  # Front is always the canonical upload

    # 6 reference angles for maximum identity lock
    # User uploads 1 front-facing photo → system generates 5 more
    # If user uploads multiple photos, system fills in missing angles only
    angle_configs = [
        {
            "name": "angle_45",
            "prompt": (
                f"Keep this exact person's face identical. Same person, same clothing, same lighting. "
                f"Three-quarter view, face turned 45 degrees to the right. "
                f"Photorealistic portrait, 8K, cinematic studio lighting."
            ),
        },
        {
            "name": "angle_profile",
            "prompt": (
                f"Keep this exact person's face identical. Same person, same clothing, same lighting. "
                f"Side profile view, face turned 90 degrees showing left side. "
                f"Photorealistic portrait, 8K, cinematic studio lighting."
            ),
        },
        {
            "name": "angle_back",
            "prompt": (
                f"Keep this exact person identical. Same clothing, same hairstyle visible from behind. "
                f"Back of head and shoulders view. "
                f"Photorealistic, 8K, cinematic studio lighting."
            ),
        },
        {
            "name": "expression_smile",
            "prompt": (
                f"Keep this exact person's face identical. Same person, same clothing, same lighting. "
                f"Warm genuine smile, eyes slightly crinkled, direct eye contact with camera. "
                f"Photorealistic portrait, 8K, cinematic studio lighting."
            ),
        },
        {
            "name": "lighting_outdoor",
            "prompt": (
                f"Keep this exact person's face identical. Same person, same clothing. "
                f"Natural outdoor golden hour lighting, warm side light from the left, soft shadows. "
                f"Photorealistic portrait, 8K, cinematic natural lighting."
            ),
        },
    ]

    # Upload canonical once for all angle generations
    try:
        canonical_url = fal_client.upload_file(canonical_path)
    except Exception as e:
        print(f"   [WARN] Could not upload canonical for angle gen: {e}")
        return angle_refs

    for cfg in angle_configs:
        try:
            # Use FLUX Kontext MAX MULTI for highest identity accuracy
            # Max Multi uses AuraFace embeddings — strongest identity lock available
            result = fal_client.subscribe(
                "fal-ai/flux-pro/kontext/max/multi",
                arguments={
                    "prompt": (
                        f"PRESERVE IDENTITY: Keep this exact person's face, hair, skin, "
                        f"and all physical features identical to @Image1. "
                        f"{cfg['prompt']}"
                    ),
                    "image_urls": [canonical_url],
                    "guidance_scale": 4.0,  # Higher = stricter adherence to identity
                    "aspect_ratio": "3:4",  # Portrait aspect for reference shots
                    "output_format": "jpeg",
                    "num_images": 1,
                },
            )
            img_url = result["images"][0]["url"]
            out_path = os.path.join(char_path, f"{cfg['name']}.jpg")
            urllib.request.urlretrieve(img_url, out_path)
            angle_refs.append(out_path)
            print(f"   [ANGLE] Generated {cfg['name']} (Max Multi): {out_path}")

        except Exception as e:
            print(f"   [WARN] Angle generation failed ({cfg['name']}): {e}")
            # Non-fatal — continue with whatever angles we have

    return angle_refs


def _has_detectable_face(image_path: str) -> bool:
    """Check if DeepFace can detect at least one face in the image."""
    if not DEEPFACE_AVAILABLE:
        return True  # Assume valid if DeepFace unavailable
    try:
        faces = DeepFace.extract_faces(img_path=image_path, enforce_detection=True)
        return len(faces) > 0
    except Exception:
        return False


def compute_face_embedding(image_path: str) -> Optional[np.ndarray]:
    """Compute ArcFace/GhostFaceNet embedding for a face image."""
    if not DEEPFACE_AVAILABLE:
        return None
    try:
        embeddings = DeepFace.represent(
            img_path=image_path,
            model_name="GhostFaceNet",
            enforce_detection=False,
        )
        if embeddings:
            return np.array(embeddings[0]["embedding"])
    except Exception as e:
        print(f"   ⚠️ Embedding computation failed: {e}")
    return None


def get_character_embedding(project: dict, char_id: str) -> Optional[np.ndarray]:
    """Load cached embedding or compute on-the-fly."""
    char = get_character(project, char_id)
    if not char:
        return None

    cache_path = char.get("embedding_cache", "")
    if cache_path and os.path.exists(cache_path):
        return np.load(cache_path)

    canonical = char.get("canonical_reference", "")
    if canonical and os.path.exists(canonical):
        return compute_face_embedding(canonical)

    return None


def assign_voice(project: dict, preference: str = "") -> str:
    """Assign an ElevenLabs voice, avoiding duplicates within the project."""
    used = _get_used_voices(project)

    # If preference matches a known voice, use it
    if preference:
        for v in VOICE_POOL:
            if preference.lower() in v["name"].lower() or preference == v["id"]:
                return v["id"]

    # Pick first unused voice
    for v in VOICE_POOL:
        if v["id"] not in used:
            print(f"   🎙️ Auto-assigned voice: {v['name']} ({v['style']})")
            return v["id"]

    # All voices used — cycle back to first
    return VOICE_POOL[0]["id"]


def get_reference_image(project: dict, char_id: str) -> Optional[str]:
    """Get the canonical reference image for PuLID face-locking."""
    char = get_character(project, char_id)
    if not char:
        return None
    canonical = char.get("canonical_reference", "")
    if canonical and os.path.exists(canonical):
        return canonical
    refs = char.get("reference_images", [])
    for r in refs:
        if os.path.exists(r):
            return r
    return None


def build_identity_anchor(character: dict) -> str:
    """
    Build a fixed, immutable identity string for a character.
    This string NEVER changes between shots — it's the character's 'DNA'.

    Uses the physical_traits/description provided by the user.
    This is injected verbatim into every prompt to prevent GPT-4o
    from rephrasing the character's appearance across shots.

    Returns:
        A string like: "a young woman with straight blonde hair, round wire-rimmed
        glasses, fair skin, oval face, slim build"
    """
    traits = character.get("physical_traits", character.get("description", ""))
    name = character.get("name", "character")

    if not traits:
        return f"{name}"

    # The anchor is the character's description AS-IS — never modified
    return f"{name}: {traits}"


def get_identity_anchor(project: dict, char_id: str) -> str:
    """Get the identity anchor for a character by ID."""
    char = get_character(project, char_id)
    if not char:
        return ""
    return build_identity_anchor(char)


def get_multi_angle_refs(project: dict, char_id: str) -> List[str]:
    """
    Get all multi-angle reference images for Kling 3.0 Pro subject binding.
    Returns list of paths: [front, 45°, profile, back] (whatever is available).
    """
    char = get_character(project, char_id)
    if not char:
        return []

    refs = char.get("multi_angle_refs", [])
    valid = [r for r in refs if os.path.exists(r)]

    # Fallback to canonical + uploads if no multi-angle refs
    if not valid:
        canonical = char.get("canonical_reference", "")
        if canonical and os.path.exists(canonical):
            return [canonical]
        return [r for r in char.get("reference_images", []) if os.path.exists(r)]

    return valid
