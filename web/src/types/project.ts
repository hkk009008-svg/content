export interface Character {
  id: string
  name: string
  description: string
  reference_images: string[]
  canonical_reference: string
  voice_id: string
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
  embedding_cache: string
}

/** Auto-approve audit entry written by cinema/auto_approve.py (Session 11).
 *  One entry per gate per check; accumulates across gates on the same shot.
 *  All consumers MUST use optional chaining — entries are absent on shots
 *  produced before Session 11. */
export interface AutoApproveAuditEntry {
  gate: 'plan' | 'image' | 'motion' | 'final'
  auto_approved: boolean
  /** Evaluation could not produce a substantive approval/veto decision.
   *  Deferred entries still require manual review and must not be counted as
   *  rule vetoes. Optional for projects written before the field existed. */
  deferred?: boolean
  vetoes: string[]
  rule_names: string[]
  timestamp: string  // ISO 8601
}

/** Safe, operator-facing projection of a provider job that was accepted but
 *  did not reach a terminal state during the request that started it. This
 *  intentionally excludes provider credentials, raw payloads, and URLs.
 *  Optional/nullable detail fields keep older and partially-populated project
 *  JSON readable while the required engine/status pair identifies the job's
 *  recovery state. */
export interface DeferredMotionJob {
  engine: string
  status: 'pending' | 'recovery_required'
  reason?: string | null
  job_id?: string | null
  provider_status?: string | null
  attempts?: string[] | null
  billed?: boolean | null
  duration_s?: number | null
  updated_at?: string | null
  resolve_after?: string | null
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
  /** Canonical shot-level dialogue survives in older projects even when a
   *  take predates metadata.has_dialogue. */
  dialogue?: string | Array<Record<string, unknown>> | null
  optimizer_cache?: {
    spec?: { purpose?: string | null } | null
    [key: string]: unknown
  } | null
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
  /** Durable ambiguity fence for keyframe generation. While present, the UI
   *  must not start or iterate a keyframe take; an operator must reconcile the
   *  saved provider job explicitly before generation can continue. */
  deferred_keyframe_job?: DeferredMotionJob | null
  /** Durable provider-resume handle. Present only while motion generation
   *  must check/resume an already-accepted provider job; cleared by the
   *  backend when that job reaches a terminal result. */
  deferred_motion_job?: DeferredMotionJob | null
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

/**
 * Per-engine project override. Intentionally NARROW — mirrors
 * `_API_ENGINE_DEFAULTS` (web_server.py), the source of truth for shape.
 * The backend reads exactly `enabled` (domain/video_engine_policy.py
 * `_is_project_disabled`) plus KLING_NATIVE's `storyboard_mode`
 * (cinema/phases/motion_render.py `_get_storyboard_mode`).
 *
 * Engine duration / resolution / audio / camera params are derived per shot
 * at dispatch (phase_c_ffmpeg.py), NOT configured here. Don't re-add fields
 * nothing reads — a typed field is a promise of configurability (ADR-080).
 */
export interface ApiEngineConfig {
  enabled: boolean
  storyboard_mode?: boolean
}

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
  // Scene Transitions (assembly cross-dissolve)
  scene_transitions?: boolean
  transition_duration?: number

  // Legacy LoRA registry snapshots. These fields are read-only historical
  // state: the product cannot train, register, or consume per-character LoRAs.
  // They remain typed only so old project JSON can round-trip unchanged.
  char_lora_paths?: Record<string, string>
  char_lora_strengths?: Record<string, number>
  char_lora_triggers?: Record<string, string>

  // -----------------------------------------------------------------
  // RETIRED MAX-QUALITY TIER — the selector + inspector UI were removed in the
  // Setup redesign (Task 8). These keys are kept ONLY as type mirrors of
  // backend-accepted global_settings fields (project_manager still round-trips
  // them); no live UI reads or writes them.
  // -----------------------------------------------------------------
  max_candidate_count?: number              // N, 1-16, default 8
  max_candidate_batch?: number              // batch size before halt check, default 4
  max_halt_threshold_composite?: number     // 0.7-1.0, default 0.92
  max_halt_threshold_arc?: number           // 0.5-1.0, default 0.85 (informational under composite_only rule)
  max_halt_min_n?: number                   // 1-8, default 4
  max_regenerate_floor_arc?: number         // 0.5-1.0, default 0.82
  max_halt_rule?: HaltRule                  // composite_only (Option 2, current default), conjunctive, budget_only
  max_quality_parallel_workers?: number     // 1-4, default 1 — per-batch candidate parallelism
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
  hires_fix_denoise?: number                // 0.4-0.6, default 0.40 (backend floors at 0.40 — pod-proven 0.25 disintegrates)
  supir_enabled?: boolean                   // SUPIR 4x upscale on hero shots, default true
  supir_steps?: number                      // 20-100, default 40 (all 5 MAX_QUALITY_TEMPLATES ship 40)
  face_detailer_enabled?: boolean           // default true for portrait/medium/action
  face_detailer_guide_size?: number         // 512/1024/2048, default 1024

  // -----------------------------------------------------------------
  // AUDIO & SYNC — TTS provider + lipsync engine preferences.
  // The orchestrator consults these before falling back to PURPOSE_API_RANKING.
  // -----------------------------------------------------------------
  tts_provider?: string                     // API key, e.g. "ELEVENLABS_V3", "CARTESIA_SONIC_2"
  default_male_voice?: string                // voice id, e.g. ElevenLabs "Eric"
  default_female_voice?: string              // voice id, e.g. ElevenLabs "Lily"
  dialogue_mode_enabled?: boolean           // route multi-line dialogue through ELEVENLABS_DIALOGUE
  forced_alignment_enabled?: boolean        // WhisperX word-level alignment + DTW correction
  dialogue_target_wpm?: number               // target words/min, atempo post-process; 0 disables pacing
  dialogue_voice_mode?: 'overlay' | 'native' // 'overlay' = TTS lip-sync over silent video (default); 'native' = engine's own embedded voice
  lipsync_quality_validation?: boolean      // SyncNet score gate after each lipsync
  lipsync_validation_threshold?: number     // 0.0-1.0, default 0.65

  // Optimistic-concurrency counter (slice 9a). Stamped by the server on
  // every successful settings write (PUT or PATCH) — never set this
  // directly; echo the last-observed value back on write so PATCH (or a
  // now-fail-closed PUT, see web_server.py's _settings_revision_established)
  // can detect a write that raced against newer state.
  revision?: number
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

/**
 * One row of the server-reconciled video-engine view
 * (`web_server.py:_project_video_engine_rows`, exposed on
 * `GET /api/config?project_id=…` as `config.video_engines`).
 *
 * This is the single source of truth for whether an engine is currently
 * selectable — it already folds in catalog lifecycle, date-effective sunset
 * policy, per-project `api_engines` disable state, aspect-ratio
 * compatibility, and runtime availability. UI code must consume `can_select`
 * / `reason` as-is and must not re-derive selectability from `api_registry`.
 */
export interface VideoEngineRow {
  key: string
  label: string
  can_select: boolean
  reason: string | null
  configured_enabled: boolean
  can_configure: boolean
  in_use: boolean
  historical: boolean
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
  denoise_default: number
  target_api: string
  video_fallbacks: string[]
  description: string
}

/** Optional max-tier override block the server may still send alongside
 *  WorkflowTemplate. Type mirror only — the max-tier selector/inspector UI was
 *  retired in the Setup redesign (Task 8); no live component reads this. */
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

export type LipsyncValidationState = 'PASS' | 'FAIL' | 'UNKNOWN'

/** Provider/cascade evidence persisted with a take. A native audio flag is
 *  evidence that the provider emitted audio, never evidence that dialogue is
 *  synchronized; only validation_state carries that quality decision. */
export interface CascadeMetadata {
  engine: string
  score?: number | null
  threshold?: number | null
  validation_state?: LipsyncValidationState | null
  native_audio_generated?: boolean | null
  fallback?: boolean
  attempts?: string[]
}

export interface TakeRecord {
  id: string
  kind: 'keyframe' | 'motion' | 'performance' | 'postprocess'
  path: string
  source_take_id?: string
  status?: string
  created_at?: string
  /** Producer-attached metadata. The typed key below is a convention, not a
   *  schema — dialogue takes persist their lip-sync cascade record here
   *  (NF-4, P1-3): read via take.metadata?.lipsync_cascade. */
  metadata?: Record<string, any> & {
    has_dialogue?: boolean
    lipsync_score?: number | null
    lipsync_validation_state?: LipsyncValidationState | null
    lipsync_cascade?: CascadeMetadata
  }
  /** Cascade decision metadata — added Session 6 (P2-3).
   *  Optional: absent on takes produced before this field existed.
   *  Consumers MUST use optional chaining: take.cascade_metadata?.engine */
  cascade_metadata?: CascadeMetadata
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
  /** P1-3 (NF-3): producer extras now pass through the SSE bridge.
   *  engine = the engine being TRIED on MOTION events (the cascade winner
   *  may differ — the take's cascade_metadata records the actual one);
   *  spent/budget arrive on BUDGET_EXCEEDED. */
  engine?: string
  spent?: number
  budget?: number
}

/** Subset of {"start","resume_checkpoint","cancel","pause","resume"} the
 *  server currently considers legal for a project
 *  (`web_server.py:_pipeline_action_authority`). "resume_checkpoint" (Slice
 *  11c) only ever appears alongside "start" -- both idle, both dispatched
 *  through `POST /generate`, distinguished only by the request body's
 *  `resume` flag. It is a DIFFERENT action from plain "resume", which
 *  un-pauses an already-running pipeline via `POST /resume`. */
export type PipelineAction = 'start' | 'resume_checkpoint' | 'cancel' | 'pause' | 'resume'

/** Resume-info summary for an on-disk checkpoint -- identical shape from
 *  both `GET /checkpoint` and the `checkpoint` key `GET /pipeline-state`
 *  threads onto its idle branch (Slice 11c;
 *  `cinema.services.checkpoint_info`). Only `resumable` is guaranteed;
 *  every other field is present exactly when `resumable` is true. */
export interface CheckpointInfo {
  resumable: boolean
  completed_scenes?: number
  total_scenes?: number
  stage?: string
  shots_done?: number
  shots_failed?: number
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
  /** Slice 8a (2026-07-30 comprehensive-unification plan) -- additive to
   *  every field above on every 200 response from
   *  `GET /api/projects/<pid>/pipeline-state`, on both the live-pipeline
   *  and disk-snapshot branches. Derived from the SAME
   *  `_running_pipelines` / `_PIPELINE_PENDING` registry that gates
   *  `/generate`, `/cancel`, `/pause`, `/resume` -- never from transport/SSE
   *  connectivity. Absent only on the distinct 404 "Project not found"
   *  error shape, which this interface does not model. */
  running: boolean
  allowed_actions: PipelineAction[]
  /** Slice 11c -- additive on the disk-snapshot (idle) branch ONLY; a
   *  live pipeline's response does not carry this key (see
   *  `web_server.py:api_pipeline_state`'s docstring). Optional here
   *  because of that branch split, not because the idle branch itself
   *  ever omits it. */
  checkpoint?: CheckpointInfo
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

export type DirectorReviewDecision =
  | 'APPROVED'
  | 'MODIFIED'
  | 'REJECTED'
  | 'REVIEW_REQUIRED'
  // Preserve forward compatibility while every unknown value is rendered
  // fail-closed as manual-review-required by the UI.
  | (string & {})

export interface DirectorReview {
  decision: DirectorReviewDecision
  violations?: string[]
  quality_score?: number | null
  reasoning?: string | null
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
  available_style_refs?: { path: string; label: string }[]          // style board references on disk
  // Purpose-based API routing (from PURPOSE_API_RANKING)
  purpose_tags?: PurposeTag[]
  purpose_api_ranking?: Record<PurposeTag, string[]>                // purpose -> ordered list of API keys
  // Billing attribution (from domain/scene_decomposer.BILLING_PROVIDERS) — keyed
  // by PROVIDER (e.g. "RUNPOD_GPU", "FAL_AI"), each value the list of engine/API
  // keys that provider bills. NOT engine-keyed — see web/src/lib/podGating.ts.
  billing_providers?: Record<string, string[]>
  // Server-reconciled video-engine selectability view (web_server.py:627
  // `_project_video_engine_rows`) — present only when `/api/config` is
  // called with a `project_id` (the rows are project-scoped: they read
  // per-project `api_engines` overrides + persisted shot targets). See
  // web/src/lib/engines.ts, the single UI-side derivation point.
  video_engines?: VideoEngineRow[]
}

// ── Part 4: Capability Dashboard ────────────────────────────────────────────

export interface CapabilityDimension {
  key: string; label: string;
  value: number | null; bar: number | null; pass: boolean | null; n_measured: number;
  n_applicable?: number;
  n_unknown?: number;
  n_failed?: number;
}

/** U3 — Final-media conformance blocks on the scorecard. Sub-blocks are null
 *  when the probe half failed (e.g. no audio stream → lufs null). */
export interface ScorecardMediaLufs {
  value: number;
  target: number;
  tolerance: number;
  pass: boolean;
}

export interface ScorecardMediaFormat {
  width: number | null;
  height: number | null;
  vcodec: string | null;
  acodec: string | null;
  pass: boolean;
}

export interface ScorecardMedia {
  lufs: ScorecardMediaLufs | null;
  format: ScorecardMediaFormat | null;
  measured_at: string | null;
}

/** Diagnostic-only policy projection. These fields describe the current
 * dormant boundary and must never be interpreted as UI reactivation flags. */
export interface LoraAvailability {
  training_available: false;
  registration_available: false;
  consumer_available: false;
  policy: 'dormant';
}

/** Read-only historical LoRA sidecar returned by the character status GET. */
export interface LoraStatus extends LoraAvailability {
  char_id: string;
  status: string;
  progress_percent: number;
  started_at?: string | null;
  finished_at?: string | null;
  lora_path?: string | null;
  quality_score?: number | null;
  image_count?: number;
  config?: Record<string, unknown> | null;
  error?: string | null;
  log_tail?: string | null;
  rejected?: boolean;
  quality_warning?: boolean;
  best_strength?: number | null;
}

/** Evidence-backed capability row (Slice 12). `status` is the AUTHORED claim
 *  (live/wired/stubbed/parked/inactive/dead); `engaged_static` is the
 *  SEPARATELY COMPUTED, mechanically-validated fact — a component cannot be
 *  `engaged_static: true` unless the server found a real, currently-resolving
 *  production consumer AND a passing evidence test for it. `reason` is
 *  always a human sentence (never a raw hash/id/anchor — those stay in the
 *  server-side diagnostic view and are never sent to this page).
 *  `runtime_availability` is kept independent of `engaged_static` per
 *  product invariant 4 (never collapse static support and runtime
 *  availability into one bit) — e.g. a capability can be structurally wired
 *  (`engaged_static: true`) yet currently `runtime_availability:
 *  'unavailable'` because a credential is missing. */
export interface CapabilityComponent {
  id: string;
  title: string;
  status: string;
  exposure: 'ui' | 'api' | 'internal' | 'cli';
  spend_kind: 'none' | 'compute_local' | 'paid_api' | 'pod_gpu';
  engaged_static: boolean;
  runtime_availability: 'available' | 'unavailable' | 'not_applicable';
  runtime_reason: string | null;
  reason: string;
}

export interface CapabilityScorecard {
  project_id: string; tier: string;
  summary: { shots_total: number; shots_clearing_all_bars: number };
  dimensions: CapabilityDimension[];
  routing: { first_try: number; fallback: number; silent_fallback: number };
  gates: Record<'plan'|'image'|'motion'|'final', { approved: number; vetoed: number; deferred?: number; top_vetoes: [string, number][] }>;
  lora_availability: LoraAvailability;
  lora: { char_id: string; strength: number | null; score: number | null; verdict: 'ok'|'warning'|'rejected' }[];
  components: CapabilityComponent[];
  per_shot: {
    shot_id: string;
    identity: number|null;
    coherence: number|null;
    motion: number|null;
    lipsync: number|null;
    lipsync_state?: LipsyncValidationState | 'NOT_APPLICABLE';
    lipsync_applicable?: boolean;
    engine: string;
  }[];
  provenance: { shot_id: string; engine: string; attempts: string[]; fallback: boolean }[];
  media: ScorecardMedia | null;
  future_dimensions: string[];
}
