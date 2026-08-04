import { Section } from '../../ui'
import { RangeRow, ToggleRow } from './controls'

interface AutoApproveSettings {
  enabled?: boolean
  final_min_lipsync?: number
  final_require_human_if_upstream_auto?: boolean
  [key: string]: unknown
}

interface Props {
  s: { auto_approve?: AutoApproveSettings }
  update: (key: string, value: unknown) => void | Promise<void>
}

/**
 * Compact operator surface for the three auto-approval controls that most
 * directly change review flow. The nested object is replaced atomically via
 * the revision-bound global-settings PATCH contract; existing, non-exposed
 * gate thresholds are preserved unchanged.
 */
export function AutoApproveSection({ s, update }: Props) {
  const settings = s.auto_approve ?? {}
  const setValue = (key: string, value: boolean | number) => {
    update('auto_approve', (current: AutoApproveSettings | undefined) => ({
      ...(current ?? settings),
      [key]: value,
    }))
  }

  return (
    <Section title="Auto-Approve">
      <div className="space-y-3">
        <ToggleRow
          label="Auto-approve eligible gates"
          checked={settings.enabled !== false}
          onChange={(value) => setValue('enabled', value)}
          hint="Applies conservative gate rules; any veto still routes the shot to manual review."
        />

        <RangeRow
          label="Final lip-sync threshold"
          value={typeof settings.final_min_lipsync === 'number' ? settings.final_min_lipsync : 0.8}
          min={0}
          max={1}
          step={0.05}
          format={(value) => value.toFixed(2)}
          onChange={(value) => setValue('final_min_lipsync', value)}
          hint="Minimum measured lip-sync score for final auto-approval."
        />

        <ToggleRow
          label="Require human after upstream auto-approval"
          checked={settings.final_require_human_if_upstream_auto !== false}
          onChange={(value) => setValue('final_require_human_if_upstream_auto', value)}
          hint="Requires a final human check when an earlier gate was auto-approved."
        />

        <p className="rounded border border-warn/30 bg-head px-2 py-1.5 text-[10px] leading-relaxed text-warn">
          UNKNOWN or unavailable lip-sync evidence always vetoes auto-approval and requires review, even when the numeric threshold is 0.
        </p>
      </div>
    </Section>
  )
}
