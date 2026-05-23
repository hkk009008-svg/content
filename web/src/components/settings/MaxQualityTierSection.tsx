import type { Project } from '../../types/project'
import { SettingsSection } from './SettingsSection'

interface Props {
  s: any
  project: Project
  update: (key: string, value: any) => void | Promise<void>
}

export function MaxQualityTierSection({ s, project, update }: Props) {
  const isMaxTier = (s.quality_tier || 'production') === 'max'

  const titleNode = (
    <h2 className="text-eyebrow-lg font-semibold uppercase tracking-widest flex items-center gap-2">
      <span className={isMaxTier ? 'text-editorial-brass' : 'text-editorial-brass'}>Max Quality Tier</span>
      {isMaxTier && (
        <span className="text-eyebrow-sm font-mono bg-editorial-brass/20 text-editorial-brass px-1.5 py-0.5 rounded">
          ACTIVE
        </span>
      )}
    </h2>
  )

  return (
    <SettingsSection titleNode={titleNode}>
      {/* TIER TOGGLE — master switch */}
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-3">
        <label className="text-eyebrow text-editorial-ivory-soft block mb-2 uppercase tracking-wider">Generation Pipeline</label>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => update('quality_tier', 'production')}
            aria-pressed={!isMaxTier}
            className={`rounded-lg px-3 py-2.5 text-left transition-all ${
              !isMaxTier
                ? 'bg-editorial-brass/10 border border-editorial-brass/40'
                : 'bg-editorial-ink-soft border border-editorial-rule opacity-60 hover:opacity-100'
            }`}>
            <div className="text-eyebrow-lg font-semibold text-editorial-ivory">Production</div>
            <p className="text-eyebrow-sm text-editorial-ivory-mute mt-0.5 leading-tight">pulid.json — single-shot, ~30s/shot. Default for throughput.</p>
          </button>
          <button
            type="button"
            onClick={() => update('quality_tier', 'max')}
            aria-pressed={isMaxTier}
            className={`rounded-lg px-3 py-2.5 text-left transition-all ${
              isMaxTier
                ? 'bg-gradient-accent text-white shadow-glow-accent'
                : 'bg-editorial-ink-soft border border-editorial-rule opacity-60 hover:opacity-100'
            }`}>
            <div className={`text-eyebrow-lg font-semibold ${isMaxTier ? 'text-white' : 'text-editorial-ivory'}`}>Max Quality</div>
            <p className={`text-eyebrow-sm mt-0.5 leading-tight ${isMaxTier ? 'text-white/80' : 'text-editorial-ivory-mute'}`}>
              pulid_max.json — N=8 best-of, ~6 min/shot. Identity ~95%+.
            </p>
          </button>
        </div>
        <p className="text-eyebrow-sm text-editorial-ivory-mute mt-2">
          Max tier auto-falls-back to production if pulid_max.json or required pod nodes are unavailable.
        </p>
      </div>

      {isMaxTier && (
        <>
          {/* Best-of-N candidate count */}
          <SliderField label="Best-of-N candidate budget" field="max_candidate_count" s={s} update={update}
            min={1} max={16} step={1} defaultValue={8}
            hint="Max candidates per shot. Adaptive halt stops earlier when threshold is met." />

          {/* Candidate batch size */}
          <SliderField label="Candidate batch (halt check interval)" field="max_candidate_batch" s={s} update={update}
            min={1} max={8} step={1} defaultValue={4}
            hint="Generate this many, then score and check halt. Smaller batch = earlier exits possible." />

          {/* Halt threshold composite */}
          <SliderField label="Halt threshold (composite)" field="max_halt_threshold_composite" s={s} update={update}
            min={0.70} max={1.00} step={0.01} defaultValue={0.92} format={(v) => v.toFixed(2)}
            hint="When best candidate's composite score (0.6 × ArcFace + 0.4 × Aesthetic v2) crosses this, halt early." />

          {/* Halt min N */}
          <SliderField label="Halt minimum N" field="max_halt_min_n" s={s} update={update}
            min={1} max={8} step={1} defaultValue={4}
            hint="Never halt before this many candidates exist, even if threshold met. Guards against single-good-seed luck." />

          {/* Regenerate floor */}
          <SliderField label="Identity regenerate floor (ArcFace)" field="max_regenerate_floor_arc" s={s} update={update}
            min={0.50} max={1.00} step={0.01} defaultValue={0.82} format={(v) => v.toFixed(2)}
            hint="After halt, if best ArcFace is below this, retry once with PuLID weight +0.15. Safety net for identity drift." />

          {/* Halt rule */}
          <div>
            <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">Halt Rule</label>
            <div className="space-y-1">
              {[
                { value: 'composite_only', label: 'Composite-only', desc: 'Halt when composite ≥ threshold. Identity folded into composite. Current default.' },
                { value: 'conjunctive', label: 'Conjunctive (composite AND arc)', desc: 'Halt only when BOTH composite ≥ threshold AND ArcFace ≥ arc threshold.' },
                { value: 'budget_only', label: 'Budget-only', desc: 'Never halt early. Always run all N candidates, pick best.' },
              ].map(opt => (
                <label key={opt.value} className="flex items-start gap-2 rounded-lg border border-editorial-rule bg-editorial-ink px-3 py-2 cursor-pointer hover:border-editorial-brass/30">
                  <input type="radio" name="halt_rule"
                    checked={(s.max_halt_rule || 'composite_only') === opt.value}
                    onChange={() => update('max_halt_rule', opt.value)}
                    className="mt-0.5 accent-editorial-brass" />
                  <div>
                    <span className="text-eyebrow text-editorial-ivory font-medium">{opt.label}</span>
                    <p className="text-eyebrow-sm text-editorial-ivory-mute leading-tight mt-0.5">{opt.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Conjunctive: surface the secondary arc threshold */}
          {s.max_halt_rule === 'conjunctive' && (
            <SliderField label="Halt threshold (ArcFace gate)" field="max_halt_threshold_arc" s={s} update={update}
              min={0.50} max={1.00} step={0.01} defaultValue={0.85} format={(v) => v.toFixed(2)}
              hint="Conjunctive rule only — best candidate's ArcFace must also clear this bar to halt." />
          )}

          {/* Per-batch parallel workers (Bundle B 2.1, 2026-05-24).
              Three discrete choices fit the operator mental model — sequential
              today, opt-in 2x or 4x when the pod can handle the concurrency.
              ComfyUI still serializes GPU work; the win is overlapping
              submit/poll/download/score with the next candidate's generation. */}
          <div>
            <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">
              Per-batch parallelism
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { value: 1, label: 'Sequential', desc: 'One candidate at a time. Default. Lowest pod load.' },
                { value: 2, label: '2 workers', desc: 'Overlap I/O + scoring with next generation. ~1.6× faster.' },
                { value: 4, label: '4 workers', desc: 'Aggressive overlap. ~3.9× faster on light scoring. Watch pod memory.' },
              ].map(opt => {
                const current = s.max_quality_parallel_workers ?? 1
                const active = current === opt.value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => update('max_quality_parallel_workers', opt.value)}
                    aria-pressed={active}
                    className={`rounded-lg px-2.5 py-2 text-left transition-all ${
                      active
                        ? 'bg-editorial-brass/10 border border-editorial-brass/40'
                        : 'bg-editorial-ink-soft border border-editorial-rule opacity-60 hover:opacity-100'
                    }`}>
                    <div className="text-eyebrow-lg font-semibold text-editorial-ivory">{opt.label}</div>
                    <p className="text-eyebrow-sm text-editorial-ivory-mute mt-0.5 leading-tight">{opt.desc}</p>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Character LoRA registry */}
          <div>
            <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">Per-Character LoRAs</label>
            <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-3 space-y-2">
              {project.characters.length === 0 ? (
                <p className="text-eyebrow text-editorial-ivory-mute italic">No characters in project. Add characters first, then assign a LoRA per character.</p>
              ) : (
                project.characters.map((char) => {
                  const loraMap = s.char_lora_paths || {}
                  const loraPath = loraMap[char.id] || ''
                  return (
                    <div key={char.id} className="flex items-center gap-2">
                      <span className="text-eyebrow text-editorial-ivory font-medium w-24 truncate" title={char.name}>{char.name}</span>
                      <input type="text"
                        value={loraPath}
                        placeholder={`loras/${char.id}.safetensors`}
                        onChange={e => update('char_lora_paths', { ...loraMap, [char.id]: e.target.value })}
                        className="flex-1 bg-editorial-ink-soft border border-editorial-rule rounded px-2 py-1 text-eyebrow text-editorial-ivory font-mono placeholder:text-editorial-ivory-mute/50" />
                      {loraPath && (
                        <button
                          type="button"
                          aria-label={`Clear LoRA for ${char.name}`}
                          onClick={() => {
                            const { [char.id]: _removed, ...rest } = loraMap
                            update('char_lora_paths', rest)
                          }}
                          className="text-eyebrow text-editorial-curtain hover:text-editorial-curtain/80 px-1.5">×</button>
                      )}
                    </div>
                  )
                })
              )}
              <p className="text-eyebrow-sm text-editorial-ivory-mute mt-1 leading-tight">
                Train per-character via ai-toolkit/kohya-ss (rank 32, fp16, ~3000 steps). Path is relative to ComfyUI's models/loras/ on the pod.
              </p>
            </div>
          </div>

          {/* Style reference paths */}
          <div>
            <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">FLUX Redux Style Board</label>
            <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-3 space-y-2">
              {(s.style_reference_paths || []).length === 0 ? (
                <p className="text-eyebrow text-editorial-ivory-mute italic">No style references. The face anchor is used as fallback.</p>
              ) : (
                (s.style_reference_paths || []).map((path: string, idx: number) => (
                  <div key={idx} className="flex items-center gap-2">
                    <input type="text"
                      value={path}
                      onChange={e => {
                        const arr = [...(s.style_reference_paths || [])]
                        arr[idx] = e.target.value
                        update('style_reference_paths', arr)
                      }}
                      className="flex-1 bg-editorial-ink-soft border border-editorial-rule rounded px-2 py-1 text-eyebrow text-editorial-ivory font-mono" />
                    <button
                      type="button"
                      aria-label={`Remove style reference ${idx + 1}`}
                      onClick={() => {
                        const arr = (s.style_reference_paths || []).filter((_: any, i: number) => i !== idx)
                        update('style_reference_paths', arr)
                      }}
                      className="text-eyebrow text-editorial-curtain hover:text-editorial-curtain/80 px-1.5">×</button>
                  </div>
                ))
              )}
              <button
                type="button"
                onClick={() => {
                  const arr = [...(s.style_reference_paths || []), '']
                  update('style_reference_paths', arr)
                }}
                className="text-eyebrow text-editorial-brass hover:text-editorial-brass/80 font-medium">+ Add reference</button>
              <p className="text-eyebrow-sm text-editorial-ivory-mute mt-1 leading-tight">
                8-15 hand-picked images defining cinematography, palette, atmosphere. Averaged via Redux for shot-to-shot style continuity.
              </p>
            </div>
          </div>

          {/* Cost / time estimate */}
          <div className="rounded-lg border border-editorial-brass/20 bg-editorial-brass/5 p-3">
            <span className="text-eyebrow text-editorial-brass font-mono font-bold uppercase">Estimated Cost</span>
            <div className="mt-1.5 grid grid-cols-2 gap-2 text-eyebrow">
              <div>
                <div className="text-editorial-ivory-mute">Per shot (avg)</div>
                <div className="text-editorial-ivory font-bold">~{Math.round((s.max_candidate_count ?? 8) * 0.75)} min</div>
              </div>
              <div>
                <div className="text-editorial-ivory-mute">60-shot short</div>
                <div className="text-editorial-ivory font-bold">~{Math.round((s.max_candidate_count ?? 8) * 0.75 * 60 / 60)} hrs</div>
              </div>
            </div>
            <p className="text-eyebrow-sm text-editorial-ivory-mute mt-1.5 leading-tight">
              Estimates assume RTX 6000 Ada (48GB) at fp16. Adaptive halt typically saves 30-50% on easy shots.
            </p>
          </div>
        </>
      )}
    </SettingsSection>
  )
}

interface SliderFieldProps {
  label: string
  field: string
  s: any
  update: (key: string, value: any) => void | Promise<void>
  min: number
  max: number
  step: number
  defaultValue: number
  hint: string
  format?: (v: number) => string
}

function SliderField({ label, field, s, update, min, max, step, defaultValue, hint, format }: SliderFieldProps) {
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
        className="w-full accent-editorial-brass h-1"
        aria-label={label}
      />
      <p className="text-eyebrow-sm text-editorial-ivory-mute">{hint}</p>
    </div>
  )
}
