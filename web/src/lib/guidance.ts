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
      default_video_api: 'KLING_NATIVE',
      lip_sync_mode: 'auto',
      face_swap_enabled: true,
      reactor_enabled: true,
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
      default_video_api: 'AUTO',
      music_mood: 'melancholic',
      adaptive_pulid: true,
      identity_strictness: 0.7,
      coherence_check_enabled: true,
      color_grade_preset: 'warm_cinema',
      quality_cost_weight: 0.9,
    },
  },
  {
    id: 'kinetic_action',
    label: 'Kinetic Action',
    summary: 'Prioritizes motion physics, smoother movement, and stronger motion gates.',
    useWhen: 'Chase, impact, stunts, aggressive camera movement.',
    settings: {
      default_video_api: 'SORA_NATIVE',
      music_mood: 'action',
      motion_quality_threshold: 0.55,
      rife_enabled: true,
      video_upscale_enabled: true,
      color_grade_preset: 'high_contrast',
      quality_cost_weight: 0.85,
    },
  },
  {
    id: 'worldbuilding',
    label: 'Worldbuilding',
    summary: 'Use for environment-first footage where atmosphere and scale matter more than facial fidelity.',
    useWhen: 'Establishers, skylines, travel shots, empty spaces, mood footage.',
    settings: {
      default_video_api: 'LTX',
      music_mood: 'ethereal',
      color_grade_preset: 'golden_hour',
      coherence_check_enabled: true,
      identity_strictness: 0.5,
      quality_cost_weight: 0.75,
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
