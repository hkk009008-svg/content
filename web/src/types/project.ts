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

export type SurfaceType = 'matte' | 'glossy' | 'metallic' | 'translucent' | 'mixed'

/** Product / prop asset for commercial work. Treated as a first-class subject
 *  with reference-image conditioning + identity validation. */
export interface ProductObject {
  id: string
  name: string
  brand: string
  description: string
  reference_images: string[]
  canonical_reference: string
  material_traits: string         // e.g., "brushed aluminum body, matte black plastic accents"
  surface_type: SurfaceType
  branding_constraints: string    // e.g., "logo must be visible, legible, centered"
  scale_reference: string         // e.g., "fits in adult hand, ~6cm tall"
  texture_anchor: string          // critical visual features: logo, badge, signature color
  ip_adapter_weight: number
  embedding_cache: string
}

/** Auto-approve audit entry written by cinema/auto_approve.py (Session 11).
 *  One entry per gate per check; accumulates across gates on the same shot.
 *  All consumers MUST use optional chaining — entries are absent on shots
 *  produced before Session 11. */
export interface AutoApproveAuditEntry {
  gate: 'plan' | 'image' | 'motion' | 'final'
  auto_approved: boolean
  vetoes: string[]
  rule_names: string[]
  timestamp: string  // ISO 8601
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
  objects_in_frame: string[]
  primary_object: string
  // Performance capture (handoff §4)
  performance_takes?: TakeRecord[]
  approved_performance_take_id?: string
  performance_engine?: 'ACT_ONE' | 'LIVE_PORTRAIT' | 'VIGGLE' | 'SKIP' | ''
  driving_video_path?: string
  shot_type?: string
  action_context: string
  generated_image: string
  generated_video: string
  plan_status: 'pending_review' | 'approved' | 'rejected'
  plan_rejection_reason?: string
  keyframe_takes: TakeRecord[]
  approved_keyframe_take_id: string
  motion_takes: TakeRecord[]
  approved_motion_take_id: string
  postprocess_variants: TakeRecord[]
  approved_final_take_id: string
  diagnostics: ShotDiagnostic[]
  intent_notes: string
  negative_constraints: string
  continuity_constraints: string
  // Auto-approve fields — all optional for backward compat with pre-S11 projects.
  // S11 sets <gate>_auto_approved=true when the gate passed without operator review.
  // S12 adds motion_auto_approved when CINEMA_AUTO_APPROVE_MOTION=1 was set during the run.
  plan_auto_approved?: boolean
  image_auto_approved?: boolean
  motion_auto_approved?: boolean   // present only when CINEMA_AUTO_APPROVE_MOTION=1
  final_auto_approved?: boolean
  auto_approve_audit?: AutoApproveAuditEntry[]
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

export type QualityTier = 'production' | 'max'
export type HaltRule = 'composite_only' | 'conjunctive' | 'budget_only'
export type ReduxStrength = 'high' | 'medium' | 'low'

export interface GlobalSettings {
  aspect_ratio: string
  language?: string           // Project dialogue language. English | Korean | Japanese | Mandarin | Spanish | French | German | Hindi | Arabic | Portuguese | Italian | Russian
  music_mood: string
  color_palette: string
  style_rules: Record<string, string>
  // Audio
  music_mastering?: string
  // ComfyUI (production tier)
  comfyui_sampler?: string
  comfyui_steps?: number
  flux_guidance?: number
  // Post-Processing
  color_grade_preset?: string
  lip_sync_mode?: string
  face_swap_enabled?: boolean
  motion_quality_threshold?: number
  // Quality
  identity_retry_max?: number
  coherence_threshold?: number
  // API Engines
  cascade_retry_limit?: number
  api_engines?: Record<string, ApiEngineConfig>
  // V11: Budget gate (read by cinema/core.py via CostTracker)
  budget_limit_usd?: number
  // V11: Quality Engine
  identity_strictness?: number
  // V11: LLM model override (read by llm/chief_director.py per call)
  creative_llm?: string
  // V11: Adaptive PuLID gate (read by domain/continuity_engine.py)
  adaptive_pulid?: boolean
  // V11: Workflow & Coherence
  coherence_check_enabled?: boolean
  color_drift_sensitivity?: number

  // -----------------------------------------------------------------
  // MAX-QUALITY TIER — opt-in via quality_tier='max'.
  // Powers the N=8 adaptive best-of pipeline (quality_max.py).
  // Defaults below if undefined mirror MAX_QUALITY_TEMPLATES values.
  // -----------------------------------------------------------------
  quality_tier?: QualityTier
  max_candidate_count?: number              // N, 1-16, default 8
  max_candidate_batch?: number              // batch size before halt check, default 4
  max_halt_threshold_composite?: number     // 0.7-1.0, default 0.92
  max_halt_threshold_arc?: number           // 0.5-1.0, default 0.85 (informational under composite_only rule)
  max_halt_min_n?: number                   // 1-8, default 4
  max_regenerate_floor_arc?: number         // 0.5-1.0, default 0.82
  max_halt_rule?: HaltRule                  // composite_only (Option 2, current default), conjunctive, budget_only
  max_quality_parallel_workers?: number     // 1-4, default 1 — per-batch candidate parallelism
  char_lora_paths?: Record<string, string>  // character_id -> LoRA .safetensors path
  style_reference_paths?: string[]          // FLUX Redux style board references

  // -----------------------------------------------------------------
  // ComfyUI Engine extensions — only meaningful in max tier.
  // -----------------------------------------------------------------
  slg_scale?: number                        // Skip Layer Guidance, 0-5, default 2.5
  freeu_b1?: number                         // FreeU v2 backbone amplifier 1, default 1.3
  freeu_b2?: number                         // FreeU v2 backbone amplifier 2, default 1.4
  freeu_s1?: number                         // FreeU v2 skip dampener 1, default 0.9
  freeu_s2?: number                         // FreeU v2 skip dampener 2, default 0.2
  detail_daemon_amount?: number             // 0-1, default 0.5
  controlnet_canny_strength?: number        // 0-0.5, default 0.15
  controlnet_pose_strength?: number         // 0-0.5, default 0.35
  controlnet_tile_strength?: number         // 0-0.5, default 0.25
  redux_strength?: ReduxStrength            // FLUX Redux style strength, default 'high'
  ays_steps?: number                        // Align Your Steps step count, 15-40, default 28
  hires_fix_enabled?: boolean               // 1.5x latent upscale + 2nd pass, default true
  hires_fix_denoise?: number                // 0.2-0.6, default 0.40
  supir_enabled?: boolean                   // SUPIR 4x upscale on hero shots, default true
  supir_steps?: number                      // 20-100, default 50
  face_detailer_enabled?: boolean           // default true for portrait/medium/action
  face_detailer_guide_size?: number         // 512/1024/2048, default 1024

  // -----------------------------------------------------------------
  // AUDIO & SYNC — TTS provider + lipsync engine preferences.
  // The orchestrator consults these before falling back to PURPOSE_API_RANKING.
  // -----------------------------------------------------------------
  tts_provider?: string                     // API key, e.g. "ELEVENLABS_V3", "CARTESIA_SONIC_2"
  dialogue_mode_enabled?: boolean           // route multi-line dialogue through ELEVENLABS_DIALOGUE
  forced_alignment_enabled?: boolean        // WhisperX word-level alignment + DTW correction
  // Lipsync engine priority — drag-rank in UI; first available wins.
  lipsync_engine_priority?: string[]        // e.g. ["HEDRA_C3", "SYNC_SO_V3", "MUSETALK", "OMNIHUMAN_V1_5"]
  lipsync_quality_validation?: boolean      // SyncNet score gate after each lipsync
  lipsync_validation_threshold?: number     // 0.0-1.0, default 0.65
}

export type ApiModality = 'video' | 'image' | 'lipsync' | 'tts' | 'music' | 'foley' | 'upscale'
export type ApiStatus = 'live' | 'beta' | 'planned'
export type PurposeTag =
  | 'dialogue_close_up'
  | 'talking_head_full'
  | 'action_motion'
  | 'static_portrait'
  | 'establishing_shot'
  | 'macro_detail'
  | 'style_locked_sequence'
  | 'narration'
  | 'music_score'
  | 'foley'
  | 'upscale_image'
  | 'upscale_video'

export interface ApiInfo {
  label: string
  category: 'smart' | 'native' | 'fal_proxy' | 'lipsync' | 'tts' | 'music' | 'foley' | 'image_gen' | 'upscale'
  description: string
  // Purpose-routing metadata (additive — older code reading only label/category/description still works)
  modality?: ApiModality
  best_for?: PurposeTag[]
  per_shot_cost?: number       // estimated USD per invocation
  quality_score?: number       // [0, 1] subjective quality
  latency_s?: number           // typical wall-clock seconds
  status?: ApiStatus
  native_audio?: boolean       // true for Veo / Sora-class models that emit audio
}

export interface PurposeRanking {
  purpose: PurposeTag
  ranked: { key: string; info: ApiInfo }[]
}

export interface WorkflowTemplate {
  pulid_weight: number
  pulid_start_at: number
  pulid_end_at: number
  guidance: number
  steps: number
  sampler: string
  scheduler: string
  pag_scale: number
  controlnet_depth_strength: number
  ip_adapter_weight: number
  denoise_default: number
  target_api: string
  video_fallbacks: string[]
  description: string
}

/** Optional max-tier override block sent by the server alongside WorkflowTemplate.
 *  When the user flips quality_tier to "max" the UI surfaces these instead. */
export interface MaxQualityTemplate {
  candidate_count: number
  candidate_batch: number
  halt_threshold_composite: number
  halt_threshold_arc: number
  halt_min_n: number
  regenerate_floor_arc: number
  pulid_weight: number
  pulid_start_at: number
  pulid_end_at: number
  lora_strength_model: number
  lora_strength_clip: number
  guidance: number
  ays_steps: number
  sampler: string
  pag_scale: number
  slg_scale: number
  freeu_b1: number
  freeu_b2: number
  freeu_s1: number
  freeu_s2: number
  detail_daemon_amount: number
  cn_depth_strength: number
  cn_canny_strength: number
  cn_pose_strength: number
  cn_tile_strength: number
  redux_strength: ReduxStrength
  redux_end_at: number
  latent_blend_ratio: number
  hires_fix_enabled: boolean
  hires_fix_scale: number
  hires_fix_denoise: number
  hires_fix_steps: number
  face_detailer_enabled: boolean
  face_detailer_guide_size: number
  face_detailer_denoise: number
  supir_enabled: boolean
  supir_steps: number
  supir_cfg_scale: number
  final_resolution: [number, number]
  target_api: string
  video_fallbacks: string[]
  description: string
}

export interface Project {
  id: string
  name: string
  characters: Character[]
  locations: Location[]
  objects: ProductObject[]
  scenes: Scene[]
  global_settings: GlobalSettings
}

export interface TakeRecord {
  id: string
  kind: 'keyframe' | 'motion' | 'postprocess'
  path: string
  source_take_id?: string
  status?: string
  created_at?: string
  metadata?: Record<string, any>
  /** Cascade decision metadata — added Session 6 (P2-3).
   *  Optional: absent on takes produced before this field existed.
   *  Consumers MUST use optional chaining: take.cascade_metadata?.engine */
  cascade_metadata?: {
    engine: string        // which engine actually produced this take
    score?: number        // quality gate score (SyncNet for lipsync, not used for video)
    threshold?: number    // the gate bar that was checked
    fallback?: boolean    // true if restored from stash after no engine cleared threshold
    attempts?: string[]   // engines tried in order, oldest first (includes the winning engine)
  }
}

export interface ShotDiagnostic {
  created_at: string | number
  take_id: string
  take_kind: string
  scores: Record<string, number>
  recommendations: { tool: string; reason: string }[]
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
  video_url?: string
  take_id?: string
  take_kind?: string
  identity_score?: number
  director_review?: DirectorReview
  coherence_score?: number
  motion_score?: number
  shot_type?: string
  failure_reason?: string
  quality_metrics?: QualityMetrics
  gate_status?: GateStatus
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
  gate_status: GateStatus
}

export interface GateStatus {
  total_shots: number
  plans_approved: number
  keyframes_approved: number
  motions_generated: number
  finals_approved: number
}

// --- Pipeline Mode Types ---

export type ShotStatus =
  | 'pending'
  | 'plan_review'
  | 'generating_image'
  | 'image_review'
  | 'generating_video'
  | 'final_review'
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
  take_id?: string
  take_kind?: string
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
  workflow_templates?: Record<string, WorkflowTemplate>
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
  // Max-tier configuration surface (read from MAX_QUALITY_TEMPLATES on the server)
  max_workflow_templates?: Record<string, MaxQualityTemplate>
  available_loras?: { id: string; path: string; label: string }[]   // LoRA registry (server-side scan)
  available_style_refs?: { path: string; label: string }[]          // style board references on disk
  // Purpose-based API routing (from PURPOSE_API_RANKING)
  purpose_tags?: PurposeTag[]
  purpose_api_ranking?: Record<PurposeTag, string[]>                // purpose -> ordered list of API keys
}
