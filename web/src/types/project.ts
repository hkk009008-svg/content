export interface Character {
  id: string
  name: string
  description: string
  reference_images: string[]
  canonical_reference: string
  voice_id: string
  ip_adapter_weight: number
  physical_traits: string
  embedding_cache: string
}

export interface Location {
  id: string
  name: string
  description: string
  reference_images: string[]
  prompt_fragment: string
  lighting: string
  time_of_day: string
  weather: string
  seed: number
}

export interface Shot {
  id: string
  prompt: string
  camera: string
  visual_effect: string
  target_api: string
  scene_foley: string
  characters_in_frame: string[]
  primary_character: string
  action_context: string
  generated_image: string
  generated_video: string
}

export interface Scene {
  id: string
  order: number
  title: string
  location_id: string
  characters_present: string[]
  action: string
  dialogue: string
  mood: string
  camera_direction: string
  duration_seconds: number
  num_shots: number
  shots: Shot[]
}

export interface ApiEngineConfig {
  enabled: boolean
  duration?: string | number
  resolution?: string
  face_consistency?: boolean
  storyboard_mode?: boolean
  generate_audio?: boolean
  camera_motion_native?: boolean
}

export interface GlobalSettings {
  aspect_ratio: string
  music_mood: string
  color_palette: string
  master_seed: number
  style_rules: Record<string, string>
  default_video_api: string
  // Audio
  narration_mode?: string
  narrator_voice?: string
  voice_effect?: string
  music_mastering?: string
  // ComfyUI
  pag_scale?: number
  controlnet_depth_strength?: number
  ip_adapter_style_weight?: number
  comfyui_upscale?: boolean
  comfyui_sampler?: string
  comfyui_steps?: number
  flux_guidance?: number
  // Post-Processing
  color_grade_preset?: string
  lip_sync_mode?: string
  face_swap_enabled?: boolean
  reactor_enabled?: boolean
  codeformer_weight?: number
  rife_enabled?: boolean
  video_upscale_enabled?: boolean
  motion_quality_threshold?: number
  // Quality
  identity_retry_max?: number
  coherence_threshold?: number
  // API Engines
  cascade_retry_limit?: number
  api_engines?: Record<string, ApiEngineConfig>
  // V11: Budget & Cost
  budget_limit_usd?: number
  cost_optimization?: string
  // V11: Quality Engine (VBench)
  vbench_overall_threshold?: number
  identity_strictness?: number
  temporal_flicker_tolerance?: number
  regression_sensitivity?: number
  // V11: LLM Preferences
  creative_llm?: string
  quality_judge_llm?: string
  competitive_generation?: boolean
  // V11: Workflow & Coherence
  quality_cost_weight?: number
  adaptive_pulid?: boolean
  coherence_check_enabled?: boolean
  color_drift_sensitivity?: number
}

export interface ApiInfo {
  label: string
  category: 'smart' | 'native' | 'fal_proxy'
  description: string
}

export interface Project {
  id: string
  name: string
  characters: Character[]
  locations: Location[]
  scenes: Scene[]
  global_settings: GlobalSettings
}

export interface QualityMetrics {
  identity_score?: number
  shot_type?: string
  [key: string]: number | string | undefined  // per-character scores like char_Alex_sim
}

export interface ProgressEvent {
  stage: string
  detail: string
  percent: number
  scene_id?: string
  shot_id?: string
  image_url?: string
  identity_score?: number
  director_review?: DirectorReview
  coherence_score?: number
  motion_score?: number
  shot_type?: string
  failure_reason?: string
  quality_metrics?: QualityMetrics
}

export interface PipelineState {
  paused: boolean
  cancelled: boolean
  current_stage: string
  current_scene_id: string
  current_shot_id: string
  shot_results: Record<string, { image: string | null; video: string | null; identity_score: number; status: string }>
  failed_shots: string[]
  scenes_completed: number
}

// --- Pipeline Mode Types ---

export type ShotStatus =
  | 'pending'
  | 'generating_image'
  | 'image_review'
  | 'generating_video'
  | 'post_processing'
  | 'complete'
  | 'failed'

export interface StructuredPrompt {
  shot: string
  scene: string
  action: string
  outfit: string
  quality: string
  raw: string
}

export interface DirectorReview {
  decision: 'APPROVED' | 'MODIFIED' | 'REJECTED'
  violations: string[]
  quality_score: number
  reasoning: string
}

export interface ShotState {
  id: string
  shot_index: number
  scene_id: string
  status: ShotStatus
  prompt: string
  camera: string
  target_api: string
  generated_image: string | null
  identity_score: number | null
  generated_video: string | null
  approved: boolean | null
  retry_count: number
  coherence_score?: number | null
  motion_score?: number | null
  shot_type?: string
  failure_reason?: string
  quality_metrics?: QualityMetrics
}

export type StageStatus = 'pending' | 'running' | 'complete' | 'failed'

export interface PipelineStage {
  id: string
  label: string
  status: StageStatus
}

export interface AppConfig {
  camera_motions: string[]
  visual_effects: string[]
  target_apis: string[]
  api_registry: Record<string, ApiInfo>
  music_moods: string[]
  voice_pool: { id: string; name: string; style: string }[]
  aspect_ratios: string[]
  pacing_options: string[]
  mood_options: string[]
  post_processing: Record<string, { available: boolean; description: string }>
  continuity_options: Record<string, { min: number; max: number; default: number; description: string }>
  color_grade_presets?: string[]
  lip_sync_modes?: string[]
  api_engine_defaults?: Record<string, ApiEngineConfig>
  // V11 config options
  cost_optimization_levels?: { value: string; label: string }[]
  creative_llm_options?: { value: string; label: string }[]
  quality_judge_options?: { value: string; label: string }[]
}
