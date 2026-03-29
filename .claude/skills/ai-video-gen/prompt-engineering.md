# Prompt Engineering for AI Video Generation

## 5-Section Prompt Structure

Every video generation prompt follows this structure. Each section serves a specific purpose:

```
MOTION: [camera movement + actor movement description]
SUBJECT: [character preservation + appearance rules]
PHYSICS: [gravity, cloth, momentum, shadow constraints]
TEMPORAL: [frame-to-frame consistency rules]
QUALITY: [photorealism enforcement]
```

---

## API-Specific Prompt Templates

### Kling Native
Emphasize rigid facial structure and same clothing/skin tone (Kling's face_consistency flag works best with these cues):
```
MOTION: Smooth cinematic [camera_motion], natural acceleration and deceleration.
SUBJECT: Maintain rigid facial bone structure — zero face deformation between frames.
Same hair, skin tone, clothing pattern in every frame.
PHYSICS: Natural body movement with weight and momentum, realistic motion blur.
TEMPORAL: Consistent inter-frame luminance, stable color temperature, no flickering.
QUALITY: Photorealistic cinematic footage, high definition, consistent volumetric lighting.
```

### Sora Native
Emphasize physics, gravity, and cloth simulation (Sora's strongest capability):
```
MOTION: Smooth cinematic [camera_motion], natural acceleration.
SUBJECT: Maintain exact character appearance throughout.
PHYSICS: Natural body movement with weight and momentum, realistic motion blur,
consistent gravity, cloth physics responding to movement.
TEMPORAL: Consistent luminance, stable color temperature, no flickering.
QUALITY: Photorealistic cinematic footage, natural film grain.
```

### Veo Native
Emphasize reference image preservation (Veo uses reference images differently):
```
MOTION: Smooth cinematic [camera_motion], natural acceleration.
PRESERVE: Maintain exact character appearance from reference images.
PHYSICS: Natural body weight and momentum, cloth physics, realistic shadows.
TEMPORAL: Consistent luminance, stable color temperature, no flickering.
QUALITY: Photorealistic cinematic footage, consistent volumetric lighting.
```

### LTX
Keep prompts shorter — LTX responds well to concise, direct prompts:
```
MOTION: Smooth cinematic [camera_motion].
PRESERVE: Maintain character appearance and environment consistency.
QUALITY: Photorealistic cinematic footage, natural motion, no artifacts.
```

---

## Global Negative Prompt

Applied to ALL APIs (where negative prompt is supported):

```
blur, distortion, deformed face, identity change, face morph, extra limbs,
floating objects, flickering, temporal inconsistency, plastic skin,
over-smoothed texture, unnatural eye movement, teeth distortion,
clothing pattern change, sudden lighting shift, smearing motion blur
```

---

## Photorealism Formula

Appended to every image generation prompt via Style Director:

> Visible skin pores with subsurface scattering, shallow depth of field f/1.4–2.8 with circular bokeh, natural film grain ISO 400, micro-detail in fabric weave and material texture, volumetric atmospheric lighting, no AI artifacts, no smooth plastic skin, no over-saturated colors.

---

## Camera Motion Options

9 supported camera motions from scene decomposition:

| Motion | Prompt Implication | Best Shot Types |
|--------|-------------------|-----------------|
| `zoom_in_slow` | Intimate focus, building tension | Portrait, medium |
| `zoom_out_slow` | Reveal, establishing context | Wide, landscape |
| `zoom_in_fast` | Dramatic emphasis | Action |
| `pan_right` | Following subject, natural flow | Medium, action |
| `pan_left` | Following subject, reverse flow | Medium, action |
| `pan_up_crane` | Ascending reveal, grandeur | Wide, landscape |
| `pan_down` | Descending, grounding | Medium |
| `static_drone` | Overhead establishing | Landscape |
| `dolly_in_rapid` | Aggressive approach | Action |

**LTX additional motions**: dolly_out, jib_up, jib_down, tilt_up, tilt_down, crane_up, crane_down, truck_left, truck_right, static (15 total via camera_motion parameter)

---

## Transition Prompts

From `_build_transition_prompt()` — mood-aware transitions between shots:

| Transition Type | Condition | Prompt Pattern |
|----------------|-----------|----------------|
| Dark → Light | Previous mood dark, next light | "sunrise-like illumination gradually filling frame" |
| Light → Dark | Previous mood light, next dark | "colors desaturating, shadows deepening" |
| Same Mood | Moods match | "smooth continuous flow maintaining atmosphere" |
| Cross-Mood | Different moods | "cinematic match cut transitioning emotional tone" |

---

## Parameter Tuning Rules of Thumb

### PuLID Weight Adjustment
- **Increase by 0.1 if**: Identity validator fails repeatedly (but NOT for FACE_ANGLE_EXTREME or SMALL_FACE_REGION)
- **Decrease by 0.05 if**: Face looks uncanny or plastic
- **Range**: 0.0–1.0 (clamped)

### Guidance Scale
- **Increase by 0.5 if**: Prompt not being followed accurately
- **Decrease by 0.5 if**: Over-saturated colors, unnatural appearance
- **Safe range**: 3.0–4.0 (3.5 is FLUX sweet spot)

### Steps
- **Increase by 5 if**: Visible noise or graininess
- **Decrease by 5 if**: Too slow and quality is acceptable
- **Range**: 10–30 (portrait: 25, action/medium: 20)

### PAG Scale (Perturbed Attention Guidance)
- **3.5**: Maximum detail sharpening (landscapes, architecture)
- **3.0**: Portrait/medium sweet spot
- **2.5**: Wide shots (avoid over-sharpening distance)
- **2.0**: Action/motion (allow dynamic softness)

### ControlNet Depth Strength
- **0.55**: Landscape — strongest architectural preservation
- **0.50**: Wide — prevent environment drift
- **0.40**: Medium — balanced spatial and face
- **0.35**: Portrait — face is priority over background
- **0.30**: Action — allow motion freedom

### IP-Adapter Weight
- **0.40**: Landscape — lock atmosphere and color
- **0.35**: Wide — environment consistency
- **0.30**: Medium — balanced style transfer
- **0.25**: Portrait/action — face is priority

---

## Prompt Anti-Patterns (What NOT to Do)

1. **Don't put negative concepts in positive prompts**: "Not blurry" doesn't work — use negative prompts
2. **Don't conflict**: "fast AND slow movement" confuses all models
3. **Don't over-specify minutiae**: Let the model infer — over-specifying minor details (button colors, shoelace patterns) often degrades overall quality
4. **Don't exceed 2 sentences per section**: Prompts are not essays — concise and structural wins
5. **Don't rephrase character descriptions**: Use identity anchors verbatim — rephrasing causes cumulative drift
6. **Don't omit TEMPORAL section**: Without it, inter-frame flickering increases dramatically
7. **Don't use the same prompt for all APIs**: Each API has specific strengths — adapt the emphasis accordingly

---

## Visual Effect Options

Per-shot visual effects applied during FFmpeg normalization:

| Effect | Description | Best For |
|--------|-------------|----------|
| `gritty_contrast` | High contrast, desaturated | Noir, thriller, gritty drama |
| `cinematic_glow` | Soft highlight bloom | Romantic, ethereal scenes |
| `warm_golden` | Warm color temperature | Sunset, nostalgia, comfort |
| `cool_blue` | Cool color temperature | Night, clinical, sci-fi |
| `high_saturation` | Vivid colors | Fantasy, animation style |
| `film_noir` | B&W with high contrast | Period, stylized sequences |
| `dreamy_soft` | Low contrast, soft focus | Flashback, memory scenes |
