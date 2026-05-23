import { useEffect, useState } from 'react'
import type { Project, AppConfig } from '../../types/project'
import { SettingsSection } from './SettingsSection'

const API = '/api'

interface Props {
  s: any
  config: AppConfig | null
  project: Project
}

export function AdvancedSection({ s, config, project }: Props) {
  const isMaxTier = (s.quality_tier || 'production') === 'max'

  const [diskUsage, setDiskUsage] = useState<Record<string, number> | null>(null)
  const [cleaning, setCleaning] = useState(false)

  const loadDiskUsage = async () => {
    const res = await fetch(`${API}/projects/${project.id}/disk-usage`)
    if (res.ok) setDiskUsage(await res.json())
  }

  const handleCleanup = async (aggressive = false) => {
    setCleaning(true)
    await fetch(`${API}/projects/${project.id}/cleanup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ aggressive }),
    })
    setCleaning(false)
    loadDiskUsage()
  }

  useEffect(() => { loadDiskUsage() }, [project.id])

  // Update helper local to this section (matches signature of parent's `update`)
  const update = async (key: string, value: any) => {
    await fetch(`${API}/projects/${project.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_settings: { ...s, [key]: value } }),
    })
  }

  return (
    <SettingsSection title="Advanced">
      {/* FLUX Guidance Scale */}
      <Slider label="FLUX guidance scale" field="flux_guidance" s={s} update={update}
        min={2.0} max={5.0} step={0.1} defaultValue={3.5}
        hint="Prompt adherence. 3.5=FLUX sweet spot. Higher=stricter but risk oversaturation." />

      {/* Identity Retry Max */}
      <Slider label="Identity retry max" field="identity_retry_max" s={s} update={update}
        min={1} max={5} step={1} defaultValue={3}
        hint="Max video regeneration attempts when face identity fails." />

      {/* Coherence Threshold */}
      <Slider label="Coherence threshold" field="coherence_threshold" s={s} update={update}
        min={0.3} max={1.0} step={0.05} defaultValue={0.6}
        hint="Min scene coherence score (color+lighting+composition) to accept. Below = mutation retry." />

      {/* LLM Preferences */}
      <div>
        <label className="text-eyebrow text-editorial-ivory-soft block mb-2 uppercase tracking-wider">LLM Preferences</label>
        <div className="space-y-3">
          {/* Creative LLM */}
          <div>
            <label className="text-eyebrow text-editorial-ivory-mute block mb-0.5 font-mono">Creative LLM</label>
            <select value={s.creative_llm || 'auto'}
              onChange={e => update('creative_llm', e.target.value)}
              className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-1.5 text-eyebrow text-editorial-ivory">
              {(config as any)?.creative_llm_options?.map((opt: any) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              )) || (
                <>
                  <option value="auto">Auto (Router decides)</option>
                  <option value="claude-sonnet">Claude Sonnet 4</option>
                  <option value="gpt-4o">GPT-4o</option>
                </>
              )}
            </select>
            <p className="text-eyebrow-sm text-editorial-ivory-mute">Primary model for scripts, scene descriptions, prompts.</p>
          </div>

          {/* Quality vs Cost Weight */}
          <Slider label="Quality ↔ Cost weight" field="quality_cost_weight" s={s} update={update}
            min={0.5} max={1.0} step={0.05} defaultValue={0.8}
            hint="API selection bias. 0.5 = equal weight. 1.0 = quality only. Affects which API is chosen per shot." />

          {/* Adaptive PuLID Toggle */}
          <ToggleCard field="adaptive_pulid" label="Adaptive PuLID"
            desc="Auto-adjust face-lock strength based on rolling identity scores."
            s={s} update={update} />
        </div>
      </div>

      {/* Continuity Parameters */}
      {config?.continuity_options && (
        <div>
          <label className="text-eyebrow text-editorial-ivory-soft block mb-2 uppercase tracking-wider">Continuity Engine</label>
          <div className="space-y-3">
            {Object.entries(config.continuity_options).map(([key, opt]) => {
              // Controlled input: read current value from project settings,
              // fall back to server-supplied default. Earlier version used
              // defaultValue= which made the input uncontrolled and silently
              // discarded operator changes — the slider moved but nothing
              // persisted.
              const value = s[key] ?? opt.default
              return (
                <div key={key}>
                  <div className="flex justify-between text-eyebrow text-editorial-ivory-mute mb-0.5">
                    <span className="font-mono">{key.replace(/_/g, ' ')}</span>
                    <span className="text-editorial-brass font-bold">{typeof value === 'number' ? value.toFixed(2) : value}</span>
                  </div>
                  <input type="range" min={opt.min} max={opt.max} step={0.05}
                    value={value}
                    onChange={e => update(key, parseFloat(e.target.value))}
                    aria-label={key.replace(/_/g, ' ')}
                    className="w-full accent-editorial-brass h-1" />
                  <p className="text-eyebrow-sm text-editorial-ivory-mute">{opt.description}</p>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ComfyUI Engine Parameters */}
      <div>
        <label className="text-eyebrow text-editorial-ivory-soft block mb-2 uppercase tracking-wider">ComfyUI Engine</label>
        <div className="space-y-3">
          <Slider label="PAG detail enhancement" field="pag_scale" s={s} update={update}
            min={0} max={5} step={0.5} defaultValue={3.0}
            hint="Sharpens fine detail (skin pores, fabric) without oversaturating. 0=off, 3=default, 5=max" />

          <Slider label="ControlNet depth lock" field="controlnet_depth_strength" s={s} update={update}
            min={0} max={0.8} step={0.05} defaultValue={0.35}
            hint="Spatial consistency between shots. Higher = stricter layout lock. 0=off" />

          <Slider label="IP-Adapter style transfer" field="ip_adapter_style_weight" s={s} update={update}
            min={0} max={0.6} step={0.05} defaultValue={0.30}
            hint="Visual style consistency (color grade, atmosphere) from previous shot. 0=off" />

          <ToggleCard field="comfyui_upscale" label="On-GPU 4x Upscale (Real-ESRGAN)"
            desc="Upscale on RunPod GPU instead of FAL API. Output: 2688x1536"
            s={s} update={update} />

          {/* Sampler */}
          <div>
            <label className="text-eyebrow text-editorial-ivory-mute block mb-0.5 font-mono">Sampler</label>
            <select value={s.comfyui_sampler || (isMaxTier ? 'dpmpp_3m_sde_gpu' : 'dpmpp_2m')}
              onChange={e => update('comfyui_sampler', e.target.value)}
              className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-1.5 text-eyebrow text-editorial-ivory">
              <option value="dpmpp_2m">DPM++ 2M (production default)</option>
              <option value="euler">Euler (fast, lower quality)</option>
              <option value="dpmpp_2m_sde">DPM++ 2M SDE (stochastic, creative)</option>
              <option value="dpmpp_3m_sde">DPM++ 3M SDE (CPU)</option>
              <option value="dpmpp_3m_sde_gpu">DPM++ 3M SDE GPU (max-tier default, sharpest)</option>
              <option value="uni_pc">UniPC (fast convergence)</option>
            </select>
          </div>

          {/* Steps — production tier */}
          {!isMaxTier && (
            <Slider label="Sampling steps" field="comfyui_steps" s={s} update={update}
              min={10} max={40} step={1} defaultValue={20}
              hint="Higher = more detail but slower. 20 is balanced, 25+ for portraits." />
          )}

          {/* MAX-TIER ONLY */}
          {isMaxTier && <MaxTierComfyControls s={s} update={update} />}
        </div>
      </div>

      {/* Post-Processing Pipeline display */}
      {config?.post_processing && (
        <div>
          <label className="text-eyebrow text-editorial-ivory-soft block mb-2 uppercase tracking-wider">Post-Processing</label>
          <div className="space-y-1">
            {Object.entries(config.post_processing).map(([key, val]) => (
              <div key={key} className="flex items-center gap-2 bg-editorial-ink rounded-lg px-3 py-2 border border-editorial-rule">
                <div className={`w-2 h-2 rounded-full ${val.available ? 'bg-editorial-ready' : 'bg-editorial-ivory-mute'}`} />
                <span className="text-eyebrow text-editorial-ivory font-medium">{key.replace(/_/g, ' ')}</span>
                <span className="text-eyebrow-sm text-editorial-ivory-mute flex-1 text-right">{val.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Disk Usage + Cleanup */}
      <div>
        <label className="text-eyebrow text-editorial-ivory-soft block mb-2 uppercase tracking-wider">Storage</label>
        {diskUsage && (
          <div className="bg-editorial-ink border border-editorial-rule rounded-lg p-3 space-y-1.5">
            {Object.entries(diskUsage).filter(([k]) => k !== 'total').map(([k, v]) => (
              <div key={k} className="flex justify-between text-eyebrow">
                <span className="text-editorial-ivory-mute font-mono">{k}/</span>
                <span className="text-editorial-ivory">{v} MB</span>
              </div>
            ))}
            <div className="flex justify-between text-eyebrow border-t border-editorial-rule pt-1 mt-1">
              <span className="text-editorial-ivory font-bold">Total</span>
              <span className="text-editorial-brass font-bold">{diskUsage.total} MB</span>
            </div>
          </div>
        )}
        <div className="flex gap-2 mt-2">
          <button type="button" onClick={() => handleCleanup(false)} disabled={cleaning}
            className="text-eyebrow px-3 py-1.5 rounded-lg border border-editorial-rule text-editorial-ivory-mute hover:text-editorial-ivory hover:border-editorial-brass/30 flex-1">
            {cleaning ? 'Cleaning...' : 'Clean Temp Files'}
          </button>
          <button type="button" onClick={() => handleCleanup(true)} disabled={cleaning}
            className="text-eyebrow px-3 py-1.5 rounded-lg border border-editorial-curtain/30 text-editorial-curtain hover:bg-editorial-curtain/10 flex-1">
            Deep Clean
          </button>
        </div>
      </div>
    </SettingsSection>
  )
}

function MaxTierComfyControls({ s, update }: { s: any; update: (k: string, v: any) => void | Promise<void> }) {
  return (
    <>
      <div className="rounded-lg border border-editorial-brass/20 bg-editorial-brass/5 px-3 py-2 mt-2">
        <span className="text-eyebrow text-editorial-brass font-mono font-bold uppercase">Max-tier engine</span>
        <p className="text-eyebrow-sm text-editorial-ivory-mute mt-0.5">Controls below only apply when Quality Tier = Max.</p>
      </div>

      <Slider label="AYS scheduler steps" field="ays_steps" s={s} update={update}
        min={15} max={40} step={1} defaultValue={28}
        hint="Align Your Steps — NVIDIA-optimal sigma schedule for FLUX. 28 is the sweet spot." />

      <Slider label="SLG (Skip Layer Guidance)" field="slg_scale" s={s} update={update}
        min={0} max={5} step={0.1} defaultValue={2.5} format={(v) => v.toFixed(1)}
        hint="Skip-layer guidance on DiT layers 7-11. Single biggest realism toggle on FLUX. 0 = off." />

      <Slider label="DetailDaemon amount" field="detail_daemon_amount" s={s} update={update}
        min={0} max={1} step={0.05} defaultValue={0.5} format={(v) => v.toFixed(2)}
        hint="Mid-sampling sigma injection. Adds micro-texture (skin pores, fabric weave). 0 = off." />

      {/* FreeU v2 */}
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-2 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-eyebrow text-editorial-ivory font-mono">FreeU v2 (skip-connection amplify)</span>
          <span className="text-eyebrow-sm text-editorial-ivory-mute">FLUX-compatible build required on pod</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[
            { k: 'freeu_b1', label: 'b1 (backbone 1)', def: 1.3, min: 1.0, max: 1.8 },
            { k: 'freeu_b2', label: 'b2 (backbone 2)', def: 1.4, min: 1.0, max: 1.8 },
            { k: 'freeu_s1', label: 's1 (skip 1)', def: 0.9, min: 0.0, max: 1.5 },
            { k: 'freeu_s2', label: 's2 (skip 2)', def: 0.2, min: 0.0, max: 1.5 },
          ].map((f) => (
            <div key={f.k}>
              <div className="flex justify-between text-eyebrow-sm text-editorial-ivory-mute mb-0.5">
                <span className="font-mono">{f.label}</span>
                <span className="text-editorial-brass font-bold">{((s[f.k] ?? f.def) as number).toFixed(2)}</span>
              </div>
              <input type="range" min={f.min} max={f.max} step={0.05}
                value={s[f.k] ?? f.def}
                onChange={e => update(f.k, parseFloat(e.target.value))}
                aria-label={f.label}
                className="w-full accent-editorial-brass h-1" />
            </div>
          ))}
        </div>
      </div>

      {/* 4-channel Union ControlNet */}
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-2 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-eyebrow text-editorial-ivory font-mono">FLUX Union CN Pro — 4 channels</span>
          <span className="text-eyebrow-sm text-editorial-ivory-mute">total budget &lt; 1.2</span>
        </div>
        {[
          { k: 'controlnet_depth_strength', label: 'Depth (spatial anchor)', def: 0.40, max: 0.8 },
          { k: 'controlnet_canny_strength', label: 'Canny (edge coherence)', def: 0.15, max: 0.5 },
          { k: 'controlnet_pose_strength', label: 'Pose (DWPose, body+hand+face)', def: 0.35, max: 0.6 },
          { k: 'controlnet_tile_strength', label: 'Tile (texture preservation)', def: 0.25, max: 0.5 },
        ].map((c) => {
          const v = s[c.k] ?? c.def
          return (
            <div key={c.k}>
              <div className="flex justify-between text-eyebrow-sm text-editorial-ivory-mute mb-0.5">
                <span className="font-mono">{c.label}</span>
                <span className="text-editorial-brass font-bold">{(v as number).toFixed(2)}</span>
              </div>
              <input type="range" min={0} max={c.max} step={0.05}
                value={v}
                onChange={e => update(c.k, parseFloat(e.target.value))}
                aria-label={c.label}
                className="w-full accent-editorial-brass h-1" />
            </div>
          )
        })}
      </div>

      {/* Redux strength */}
      <div>
        <label className="text-eyebrow text-editorial-ivory-mute block mb-0.5 font-mono">FLUX Redux style strength</label>
        <select value={s.redux_strength || 'high'}
          onChange={e => update('redux_strength', e.target.value)}
          className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-1.5 text-eyebrow text-editorial-ivory">
          <option value="high">High — strong style lock from board</option>
          <option value="medium">Medium — balanced</option>
          <option value="low">Low — subtle influence</option>
        </select>
        <p className="text-eyebrow-sm text-editorial-ivory-mute mt-0.5">FLUX-native image conditioning. Replaces SDXL-era IP-Adapter on FLUX.</p>
      </div>

      {/* Hires fix */}
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-2 space-y-2">
        <div className="flex items-center gap-2">
          <input type="checkbox"
            checked={s.hires_fix_enabled !== false}
            onChange={e => update('hires_fix_enabled', e.target.checked)}
            aria-label="Hires-fix (Pass 2)"
            className="accent-editorial-brass" />
          <div>
            <span className="text-eyebrow text-editorial-ivory font-medium">Hires-fix (Pass 2)</span>
            <p className="text-eyebrow-sm text-editorial-ivory-mute">1.5× latent upscale + 2nd denoise pass. Adds detail ESRGAN can't fabricate.</p>
          </div>
        </div>
        {s.hires_fix_enabled !== false && (
          <div>
            <div className="flex justify-between text-eyebrow-sm text-editorial-ivory-mute mb-0.5">
              <span className="font-mono">Pass 2 denoise</span>
              <span className="text-editorial-brass font-bold">{(s.hires_fix_denoise ?? 0.40).toFixed(2)}</span>
            </div>
            <input type="range" min={0.2} max={0.6} step={0.05}
              value={s.hires_fix_denoise ?? 0.40}
              onChange={e => update('hires_fix_denoise', parseFloat(e.target.value))}
              aria-label="Pass 2 denoise"
              className="w-full accent-editorial-brass h-1" />
          </div>
        )}
      </div>

      {/* FaceDetailer */}
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-2 space-y-2">
        <div className="flex items-center gap-2">
          <input type="checkbox"
            checked={s.face_detailer_enabled !== false}
            onChange={e => update('face_detailer_enabled', e.target.checked)}
            aria-label="FaceDetailer"
            className="accent-editorial-brass" />
          <div>
            <span className="text-eyebrow text-editorial-ivory font-medium">FaceDetailer (Impact Pack)</span>
            <p className="text-eyebrow-sm text-editorial-ivory-mute">Auto-detect face → re-denoise at guide size. Recognizable → convincing.</p>
          </div>
        </div>
        {s.face_detailer_enabled !== false && (
          <div>
            <label className="text-eyebrow-sm text-editorial-ivory-mute block mb-0.5 font-mono">Guide size</label>
            <select value={s.face_detailer_guide_size ?? 1024}
              onChange={e => update('face_detailer_guide_size', parseInt(e.target.value))}
              className="w-full bg-editorial-ink-soft border border-editorial-rule rounded px-2 py-1 text-eyebrow text-editorial-ivory">
              <option value={512}>512 — fast</option>
              <option value={1024}>1024 — recommended</option>
              <option value={2048}>2048 — slow, max detail</option>
            </select>
          </div>
        )}
      </div>

      {/* SUPIR upscale */}
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-2 space-y-2">
        <div className="flex items-center gap-2">
          <input type="checkbox"
            checked={s.supir_enabled !== false}
            onChange={e => update('supir_enabled', e.target.checked)}
            aria-label="SUPIR 4× upscale"
            className="accent-editorial-brass" />
          <div>
            <span className="text-eyebrow text-editorial-ivory font-medium">SUPIR 4× upscale (replaces Real-ESRGAN)</span>
            <p className="text-eyebrow-sm text-editorial-ivory-mute">Photorealism-tuned restoration. 5-10× better than ESRGAN on faces. Adds ~35s/shot.</p>
          </div>
        </div>
        {s.supir_enabled !== false && (
          <div>
            <div className="flex justify-between text-eyebrow-sm text-editorial-ivory-mute mb-0.5">
              <span className="font-mono">SUPIR steps</span>
              <span className="text-editorial-brass font-bold">{s.supir_steps ?? 50}</span>
            </div>
            <input type="range" min={20} max={100} step={5}
              value={s.supir_steps ?? 50}
              onChange={e => update('supir_steps', parseInt(e.target.value))}
              aria-label="SUPIR steps"
              className="w-full accent-editorial-brass h-1" />
          </div>
        )}
      </div>
    </>
  )
}

function ToggleCard({ field, label, desc, s, update }: { field: string; label: string; desc: string; s: any; update: (k: string, v: any) => void | Promise<void> }) {
  return (
    <div className="flex items-center gap-2 bg-editorial-ink rounded-lg px-3 py-2 border border-editorial-rule">
      <input type="checkbox"
        checked={s[field] !== false}
        onChange={e => update(field, e.target.checked)}
        aria-label={label}
        className="accent-editorial-brass" />
      <div>
        <span className="text-eyebrow text-editorial-ivory font-medium">{label}</span>
        <p className="text-eyebrow-sm text-editorial-ivory-mute">{desc}</p>
      </div>
    </div>
  )
}

function Slider({ label, field, s, update, min, max, step, defaultValue, hint, format }: { label: string; field: string; s: any; update: (k: string, v: any) => void | Promise<void>; min: number; max: number; step: number; defaultValue: number; hint: string; format?: (v: number) => string }) {
  const value = s[field] ?? defaultValue
  const display = format ? format(value) : value
  const isInt = step >= 1
  return (
    <div>
      <div className="flex justify-between text-eyebrow text-editorial-ivory-mute mb-0.5">
        <span className="font-mono">{label}</span>
        <span className="text-editorial-brass font-bold">{display}</span>
      </div>
      <input type="range" min={min} max={max} step={step}
        value={value}
        onChange={e => update(field, isInt ? parseInt(e.target.value) : parseFloat(e.target.value))}
        aria-label={label}
        className="w-full accent-editorial-brass h-1" />
      <p className="text-eyebrow-sm text-editorial-ivory-mute">{hint}</p>
    </div>
  )
}
