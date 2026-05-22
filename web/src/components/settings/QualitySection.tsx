import { SettingsSection } from './SettingsSection'

interface Props {
  s: any
  update: (key: string, value: any) => void | Promise<void>
}

interface SliderRowProps {
  label: string
  field: string
  s: any
  update: (key: string, value: any) => void | Promise<void>
  min: number
  max: number
  step: number
  defaultValue: number
  hint: string
}

function SliderRow({ label, field, s, update, min, max, step, defaultValue, hint }: SliderRowProps) {
  const value = s[field] ?? defaultValue
  return (
    <div>
      <div className="flex justify-between text-eyebrow text-editorial-ivory-mute mb-0.5">
        <span className="font-mono">{label}</span>
        <span className="text-editorial-brass font-bold">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => update(field, parseFloat(e.target.value))}
        className="w-full accent-editorial-brass h-1"
        aria-label={label}
      />
      <p className="text-eyebrow-sm text-editorial-ivory-mute">{hint}</p>
    </div>
  )
}

export function QualitySection({ s, update }: Props) {
  return (
    <SettingsSection title="Quality Engine">
      <p className="text-eyebrow-sm text-editorial-ivory-mute">
        VBench-2.0 quality thresholds. Shots scoring below these thresholds trigger regeneration or post-processing fixes.
      </p>

      <SliderRow
        label="VBench acceptance threshold"
        field="vbench_overall_threshold"
        s={s}
        update={update}
        min={0}
        max={1}
        step={0.05}
        defaultValue={0.6}
        hint="Min overall quality score to accept a shot. Below = auto-regenerate."
      />
      <SliderRow
        label="Identity strictness"
        field="identity_strictness"
        s={s}
        update={update}
        min={0}
        max={1}
        step={0.05}
        defaultValue={0.6}
        hint="Below this score → recommends face-swap. Higher = stricter face matching."
      />
      <SliderRow
        label="Temporal flicker tolerance"
        field="temporal_flicker_tolerance"
        s={s}
        update={update}
        min={0}
        max={1}
        step={0.05}
        defaultValue={0.85}
        hint="Below this → triggers RIFE interpolation. Lower = more permissive."
      />
      <SliderRow
        label="Regression sensitivity"
        field="regression_sensitivity"
        s={s}
        update={update}
        min={0.01}
        max={0.2}
        step={0.01}
        defaultValue={0.05}
        hint="Quality drop (%) vs baseline before flagging regression. 0.05 = 5% drop triggers alert."
      />
    </SettingsSection>
  )
}
