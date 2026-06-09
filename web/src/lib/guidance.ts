import type { AppConfig, GlobalSettings, Scene, Shot, WorkflowTemplate } from '../types/project'

export type GuidedShotType = 'portrait' | 'medium' | 'wide' | 'action' | 'landscape'
export type SceneMode = 'dialogue' | 'action' | 'character' | 'worldbuilding' | 'atmosphere'

const SHOT_TYPE_KEYWORDS: Record<GuidedShotType, string[]> = {
  portrait: ['close-up', 'closeup', 'close up', 'portrait', 'ecu', 'extreme close', '85mm', 'headshot', 'tight shot'],
  action: ['tracking', 'tracking shot', 'crane', 'dolly', 'rapid', 'chase', 'running', 'action', 'dynamic', 'handheld', 'steadicam'],
  wide: ['wide shot', 'wide angle', 'establishing', '24mm', '16mm', 'full shot', 'long shot', 'master shot', 'extreme wide'],
  landscape: ['landscape', 'aerial', 'drone', 'skyline', 'panoramic', 'environment', 'scenery', 'no character'],
  medium: ['medium', '50mm', 'mid-shot', 'waist', 'hip', 'american shot', 'cowboy shot', 'two-shot'],
}

export interface ProductionPreset {
  id: string
  label: string
  summary: string
  useWhen: string
  settings: Partial<GlobalSettings>
}

export interface SceneGuidance {
  mode: SceneMode
  title: string
  recommendation: string
  coverage: string[]
  parameterTips: string[]
}

export const PRODUCTION_PRESETS: ProductionPreset[] = [
  {
    id: 'dialogue_precision',
    label: 'Dialogue Precision',
    summary: 'Best when faces, mouth shapes, and line delivery matter more than spectacle.',
    useWhen: 'Conversation, testimony, interview, confrontation.',
    settings: {
      lip_sync_mode: 'auto',
      face_swap_enabled: true,
      adaptive_pulid: true,
      identity_strictness: 0.7,
      coherence_check_enabled: true,
      color_grade_preset: 'desaturated',
      motion_quality_threshold: 0.45,
    },
  },
  {
    id: 'character_drama',
    label: 'Character Drama',
    summary: 'Optimized for emotional beats, clean faces, and continuity across coverage.',
    useWhen: 'Performance-heavy scenes, close reactions, dramatic reveals.',
    settings: {
      music_mood: 'melancholic',
      adaptive_pulid: true,
      identity_strictness: 0.7,
      coherence_check_enabled: true,
      color_grade_preset: 'warm_cinema',
    },
  },
  {
    id: 'kinetic_action',
    label: 'Kinetic Action',
    summary: 'Prioritizes motion physics, smoother movement, and stronger motion gates.',
    useWhen: 'Chase, impact, stunts, aggressive camera movement.',
    settings: {
      music_mood: 'action',
      motion_quality_threshold: 0.55,
      color_grade_preset: 'high_contrast',
    },
  },
  {
    id: 'worldbuilding',
    label: 'Worldbuilding',
    summary: 'Use for environment-first footage where atmosphere and scale matter more than facial fidelity.',
    useWhen: 'Establishers, skylines, travel shots, empty spaces, mood footage.',
    settings: {
      music_mood: 'ethereal',
      color_grade_preset: 'golden_hour',
      coherence_check_enabled: true,
      identity_strictness: 0.5,
    },
  },
  {
    id: 'max_quality',
    label: 'Max Quality (Hero Shots)',
    summary: 'N=8 adaptive best-of with composite halt. Per-character LoRA + 4-channel Union CN + Redux + hires-fix + SUPIR. ~6 min/shot, ~92% shot-to-shot continuity.',
    useWhen: 'Hero pieces, awards reels, anywhere "max quality" matters more than throughput.',
    settings: {
      quality_tier: 'max',
      max_candidate_count: 8,
      max_candidate_batch: 4,
      max_halt_threshold_composite: 0.92,
      max_halt_threshold_arc: 0.85,
      max_halt_min_n: 4,
      max_regenerate_floor_arc: 0.82,
      max_halt_rule: 'composite_only',
      // Engine extensions
      flux_guidance: 3.5,
      slg_scale: 2.5,
      freeu_b1: 1.3,
      freeu_b2: 1.4,
      freeu_s1: 0.9,
      freeu_s2: 0.2,
      detail_daemon_amount: 0.5,
      controlnet_canny_strength: 0.15,
      controlnet_pose_strength: 0.35,
      controlnet_tile_strength: 0.25,
      redux_strength: 'high',
      ays_steps: 28,
      comfyui_sampler: 'dpmpp_3m_sde_gpu',
      hires_fix_enabled: true,
      hires_fix_denoise: 0.40,
      supir_enabled: true,
      supir_steps: 40,
      face_detailer_enabled: true,
      face_detailer_guide_size: 1024,
      // Identity safety net stays tight
      adaptive_pulid: true,
      identity_strictness: 0.85,
      coherence_check_enabled: true,
    },
  },
]

function parseShotSection(prompt: string) {
  const match = prompt.toLowerCase().match(/\[shot\]\s*(.+?)(?=\[(?:scene|action|outfit|quality)\]|$)/s)
  return match ? match[1].trim() : ''
}

export function classifyShotType(shot: Pick<Shot, 'prompt' | 'camera' | 'characters_in_frame'>): GuidedShotType {
  if (!shot.characters_in_frame || shot.characters_in_frame.length === 0) {
    return 'landscape'
  }

  const prompt = (shot.prompt || '').toLowerCase()
  const search = `${parseShotSection(prompt)} ${prompt} ${(shot.camera || '').toLowerCase()}`

  for (const shotType of ['portrait', 'action', 'wide', 'landscape', 'medium'] as GuidedShotType[]) {
    if (SHOT_TYPE_KEYWORDS[shotType].some((keyword) => search.includes(keyword))) {
      return shotType
    }
  }

  return 'medium'
}

export function getShotTemplate(shot: Shot, config: AppConfig | null): WorkflowTemplate | null {
  const shotType = classifyShotType(shot)
  return config?.workflow_templates?.[shotType] || null
}

export function inferSceneMode(scene: Scene): SceneMode {
  const action = scene.action.toLowerCase()
  const dialogue = scene.dialogue.trim()
  const hasCharacters = scene.characters_present.length > 0

  if (dialogue && hasCharacters) return 'dialogue'
  if (/(chase|run|fight|crash|jump|slam|sprint|pursuit|escape|explosion)/.test(action)) return 'action'
  if (!hasCharacters) return 'worldbuilding'
  if (/(looks|stares|cries|smiles|hesitates|breathes|waits|turns slowly|holds)/.test(action)) return 'character'
  return 'atmosphere'
}

export function getSceneGuidance(scene: Scene): SceneGuidance {
  const mode = inferSceneMode(scene)
  switch (mode) {
    case 'dialogue':
      return {
        mode,
        title: 'Dialogue Coverage',
        recommendation: 'Lead with a stable medium or two-shot, then collect reactions and over-shoulder coverage. Keep speech beats separate from large physical movement.',
        coverage: [
          'Open on a medium or two-shot to establish who is speaking and where they stand.',
          'Break reactions into their own close or portrait shots.',
          'Keep each spoken beat short enough that lip sync and identity remain stable.',
        ],
        parameterTips: [
          'Use Kling or Auto for face-heavy shots.',
          'Keep camera direction simple unless the emotional turn needs movement.',
          'Use continuity constraints for eyeline, hand props, and who is frame-left/frame-right.',
        ],
      }
    case 'action':
      return {
        mode,
        title: 'Action Coverage',
        recommendation: 'Split the scene into setup, movement, and impact. One motion idea per shot gives the cleanest physics and easiest correction pass.',
        coverage: [
          'Start with a wide orienting shot so geography is clear.',
          'Use a separate shot for the major movement beat.',
          'Reserve close shots for aftermath, reaction, or detail inserts.',
        ],
        parameterTips: [
          'Prefer Sora or Auto for body momentum and motion-heavy frames.',
          'Keep durations tighter and avoid stacking multiple actions into one shot.',
          'Raise motion quality threshold if the scene depends on fluid movement.',
        ],
      }
    case 'worldbuilding':
      return {
        mode,
        title: 'Environment-First Coverage',
        recommendation: 'Let the place do the work. Start broad, then move to one or two detail inserts that explain texture, scale, or mood.',
        coverage: [
          'Open with a wide or landscape frame.',
          'Follow with one detail shot that carries atmosphere.',
          'Only introduce characters after the place feels established.',
        ],
        parameterTips: [
          'LTX or Veo is usually the right default.',
          'Put the strongest information in location, lighting, and weather.',
          'Use continuity constraints to keep time-of-day and palette stable across the sequence.',
        ],
      }
    case 'character':
      return {
        mode,
        title: 'Character Beat Coverage',
        recommendation: 'Center the emotional turn. Start readable, then move closer only when the performance needs it.',
        coverage: [
          'Begin with a medium frame that shows posture and environment.',
          'Use portrait coverage for the emotional peak or reveal.',
          'Keep wardrobe, prop placement, and screen direction stable between takes.',
        ],
        parameterTips: [
          'Auto or Kling is usually the safest path.',
          'Use intent notes to describe the emotional job of the shot.',
          'Keep negative constraints strict around identity drift and plastic skin.',
        ],
      }
    default:
      return {
        mode,
        title: 'Atmosphere Coverage',
        recommendation: 'Use the scene to establish tone. Choose fewer shots, each with a clear sensory purpose.',
        coverage: [
          'Favor one anchor shot and one texture shot over many near-duplicates.',
          'Keep action minimal and let lighting or environment carry the beat.',
          'Use decomposition once the mood and visual conditions are concrete.',
        ],
        parameterTips: [
          'Specify color palette, haze, weather, and practical light sources.',
          'Use cinematic glow or gritty contrast only when it matches the intended finish.',
          'Keep scene duration aligned with how much visual change actually happens.',
        ],
      }
  }
}
