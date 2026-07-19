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
          {/* Creative LLM — read in llm/chief_director.py:_call_llm as a per-call model override */}
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
                  <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
                  <option value="gpt-4o">GPT-4o</option>
                </>
              )}
            </select>
            <p className="text-eyebrow-sm text-editorial-ivory-mute">Per-call model override. Mismatched provider family falls back to the active client's default.</p>
          </div>

          {/* Adaptive PuLID — gated in domain/continuity_engine.py before get_adaptive_pulid_weight */}
          <ToggleCard field="adaptive_pulid" label="Adaptive PuLID"
            desc="Auto-adjust face-lock strength from rolling identity scores. Off = use shot-type defaults."
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
          {/* Sampler */}
          <div>
            <label className="text-eyebrow text-editorial-ivory-mute block mb-0.5 font-mono">Sampler</label>
            <select value={s.comfyui_sampler || 'dpmpp_2m'}
              onChange={e => update('comfyui_sampler', e.target.value)}
              className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-1.5 text-eyebrow text-editorial-ivory">
              <option value="dpmpp_2m">DPM++ 2M (production default)</option>
              <option value="euler">Euler (fast, lower quality)</option>
              <option value="dpmpp_2m_sde">DPM++ 2M SDE (stochastic, creative)</option>
              <option value="dpmpp_3m_sde">DPM++ 3M SDE (CPU)</option>
              <option value="dpmpp_3m_sde_gpu">DPM++ 3M SDE GPU (sharpest)</option>
              <option value="uni_pc">UniPC (fast convergence)</option>
            </select>
          </div>

          {/* Steps */}
          <Slider label="Sampling steps" field="comfyui_steps" s={s} update={update}
            min={10} max={40} step={1} defaultValue={20}
            hint="Higher = more detail but slower. 20 is balanced, 25+ for portraits." />
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
