# Continuity Engine & Style Direction

The continuity system ensures characters, locations, objects, and physics remain consistent throughout an entire production. It consists of 4 integrated subsystems orchestrated by `ContinuityEngine`.

---

## 1. CharacterContinuityTracker

**Source**: `continuity_engine.py`

Tracks character identity and wardrobe across all scenes.

### What It Tracks
- **Identity**: Pre-loaded embeddings from character reference images
- **Wardrobe**: Last-seen clothing description per character
- **Spatial position**: Where the character was in the previous shot (left/center/right)
- **Appearance metadata**: Logged per shot for future continuity

### Prompt Fragment Building
For each character in a shot, builds:
```
[Character Name]: [identity anchor — physical traits, immutable]
Wearing: [wardrobe from last appearance OR character default]
Position: [spatial hint from previous shot]
```

### PuLID Character Selection
- **Primary character**: First character in `characters_in_frame` list
- Primary character's canonical reference → PuLID face input
- Multi-angle references → Kling subject binding input

---

## 2. LocationPersistence

**Source**: `continuity_engine.py`

Ensures environments look identical across all shots at the same location.

### Deterministic Seeds
Each location gets a **fixed seed** derived from its ID. This seed is used for ALL image generations at that location, preventing environment drift.

### Location Prompt Fragments
Reusable fragments injected verbatim into every shot at a location:
```
Setting: [description], [lighting based on time_of_day], [weather effects].
Photorealistic, cinematic composition, rule of thirds.
```

### Weather Descriptions
| Weather | Prompt Addition |
|---------|-----------------|
| Rain | "wet reflective surfaces, rain visible through windows" |
| Snow | "cold blue-white ambient light" |
| Fog | "atmospheric haze softening background" |
| Storm | "dramatic storm lighting with occasional flashes" |
| Clear | (no addition) |

### Why Fixed Seeds Matter
Without deterministic seeds, the same "office interior" prompt can generate wildly different rooms. Fixed seeds lock the architectural layout, furniture placement, and lighting setup across the entire production.

---

## 3. PhysicsPromptEngineer

**Source**: `continuity_engine.py`

Injects physics constraints into prompts to prevent impossible visual artifacts.

### Constraint Categories

**Spatial Continuity**:
> "Characters maintain spatial positions from previous shot. No teleportation."

**Lighting Direction Lock**:
> "Lighting direction and intensity remain exactly the same as previous shot."

**Camera Transition Smoothness**:
> "Camera smoothly transitions from [previous camera] to [current camera]."

**Real-World Physics**:
> "Obey real-world physics: gravity pulls downward, reflections match scene geometry, shadows are consistent with light source direction."

**Photorealism Enforcement**:
> "Photorealistic with visible skin pores, subsurface scattering, natural film grain."

### Motion Continuity
Validates that character actions flow logically:
- Can't be running if previous shot showed them sitting (without transition)
- Walking direction must be consistent between consecutive shots
- Object positions must persist between shots

---

## 4. TemporalConsistencyManager

**Source**: `continuity_engine.py`

Manages img2img chaining between consecutive shots within a scene.

### How img2img Chaining Works
Instead of generating each shot from noise (txt2img), consecutive shots within a scene use the **previous shot's output** as the input image with controlled denoise:

```
Shot 1: txt2img (from noise) — denoise 0.55
Shot 2: img2img (from Shot 1 output) — denoise 0.30
Shot 3: img2img (from Shot 2 output) — denoise 0.30
[new location]
Shot 4: txt2img (from noise) — denoise 0.55 (chain reset)
```

### Context-Aware Denoise Values

| Context | Denoise | Rationale |
|---------|---------|-----------|
| First shot of scene | 0.55 | Maximum creative freedom — no prior context |
| Same location, consecutive | 0.30 | Tightest consistency — environment must match |
| Same location, time skip | 0.40 | Allow lighting/mood change while keeping location |
| Location change within scene | 0.50 | New environment but maintain style/color grade |

### Scene Boundary Reset
When a new location begins, the img2img chain **resets**:
- Previous shot output is NOT used as input
- Denoise returns to 0.55 (fresh generation)
- Location seed takes over for environment consistency

---

## ContinuityEngine Orchestrator

**Source**: `continuity_engine.py:enhance_shot_prompt()`

The central method that combines all 4 subsystems:

```
Input: raw shot prompt + shot metadata + project state

1. CharacterContinuityTracker → identity fragments + wardrobe + spatial hints
2. LocationPersistence → location fragment + deterministic seed
3. PhysicsPromptEngineer → physics constraints
4. TemporalConsistencyManager → img2img config (prev_image + denoise)

Output:
  enhanced_prompt = original + location_fragment + character_fragments + physics_constraints
  continuity_config = {
    prev_image: path | None,
    denoise: float,
    seed: int,
    primary_character_ref: path,
    subject_binding_refs: [paths],
    adaptive_pulid_weight: float
  }
```

---

## Style Director

**Source**: `style_director.py`

Generates global cinematography rules that are injected into every generation prompt.

### Style Rules (via GPT-4o + optional web research)

```python
{
  "director_vision":       "emotional arc and psychological impact",
  "cinematography_rules":  "camera movement philosophy, framing guidelines",
  "color_grading_palette": "primary colors, contrast, saturation, highlights/shadows",
  "lighting_rules":        "key light direction, fill ratio, practical lights, color temp",
  "sound_design":          "ambient texture philosophy",
  "photorealism_rules":    "skin texture, depth of field, lens choice, film grain",
  "composition_rules":     "rule of thirds, negative space, leading lines"
}
```

### Prompt Suffix Injection
Style rules are converted to a suffix appended to EVERY image generation prompt:
```
Color grading: [palette] | Lighting: [rules] | [photorealism] | [composition]
```

### Photorealism Formula (always appended)
> "Visible skin pores with subsurface scattering, shallow depth of field f/1.4–2.8 with circular bokeh, natural film grain ISO 400, micro-detail in fabric weave and material texture, volumetric atmospheric lighting, no AI artifacts, no smooth plastic skin, no over-saturated colors."

### Web Research Enhancement
Optional Tavily/Firecrawl research for:
- Cinematography techniques matching mood + location
- Reference film analyses for visual inspiration
- Cultural visual references for period/genre accuracy

---

## Scene Coherence Scoring

**Source**: `coherence_analyzer.py`

Quantitative analysis of visual consistency between consecutive shots.

### Three Analysis Dimensions

**1. ColorCoherenceAnalyzer**
- HSV histogram comparison (64x64 bins, normalized)
- K-means clustering of dominant colors (palette extraction)
- Returns `color_drift` score: 0.0 (identical) to 1.0 (completely different)
- **Flag**: drift > 0.3

**2. CompositionAnalyzer**
- **Brightness distribution**: Mean, std dev, key type (high-key / balanced / low-key)
- **Lighting direction**: Sobel gradient analysis detecting which side light comes from
- **Exposure shift**: Max brightness delta across shot sequence
- **Angular consistency**: 0.0–1.0 score (1.0 = same light direction)
- **Flag**: lighting_consistency < 0.5

**3. Exposure Analysis**
- Brightness delta between consecutive frames
- **Flag**: brightness_delta > 0.15

### Overall Coherence Score

```
overall = (1 - color_drift) * 0.4 + lighting_consistency * 0.3 + composition_similarity * 0.3
```

### Recommendations Engine
Based on scores, generates specific remediation suggestions:
- `color_drift > 0.3` → "Adjust color prompt to match previous shot palette"
- `lighting_consistency < 0.5` → "Match lighting direction in prompt"
- `brightness_delta > 0.15` → "Tighten denoise for temporal consistency"

---

## Chief Director QA Layer

**Source**: `chief_director.py`

A metacognitive LLM layer that sits ABOVE all other LLMs in the pipeline.

### Purpose
Validates outputs from GPT-4o scene decomposition, reviews shot prompts for structural compliance, evaluates generated images against identity requirements.

### LLM Priority
1. **Anthropic Claude** (superior structured reasoning)
2. **OpenAI GPT-4o** (fallback)

### Capabilities
- **REJECT** prompts violating hard constraints
- **REWRITE** non-compliant prompts
- Collect diagnostic data from all pipeline stages
- Provide quality scores for generated content
