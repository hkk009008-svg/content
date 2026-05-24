/**
 * AutoApproveBadge — small inline badge displayed next to an auto-approved take.
 *
 * Mirrors the CascadeBadge pattern in ReviewStage.tsx (Session 6 P2-3) —
 * same shape: rounded pill with semantic color + hover tooltip showing rule_names.
 *
 * Color semantics (matching ReviewStage.tsx formatScore):
 *   text-editorial-ready   — gate passed, auto-approved
 *   text-editorial-warn    — vetoed entry (shown for transparency in PostRunSummary)
 *
 * When onReject is provided a small "Reject" affordance is rendered that opens
 * the RejectAutoApproveModal from the parent.
 */

import type { AutoApproveAuditEntry } from '../../types/project'

interface Props {
  gate: 'plan' | 'image' | 'motion' | 'final'
  audit: AutoApproveAuditEntry[]
  onReject?: () => void   // opens RejectAutoApproveModal when clicked
}

const GATE_LABELS: Record<string, string> = {
  plan: 'Plan',
  image: 'Image',
  motion: 'Motion',
  final: 'Final',
}

export function AutoApproveBadge({ gate, audit, onReject }: Props) {
  // Use the most recent auto-approved entry for this gate (highest timestamp
  // wins — handles re-run scenarios per brief §Decisions).
  const approvedEntries = audit
    .filter(e => e.gate === gate && e.auto_approved)
    .sort((a, b) => (a.timestamp > b.timestamp ? -1 : 1))
  const entry = approvedEntries[0]

  // Nothing to render if this gate was not auto-approved.
  if (!entry) return null

  const tooltipText = entry.rule_names.length > 0
    ? `Rules: ${entry.rule_names.join(', ')}`
    : 'Auto-approved — no rules recorded'

  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      <span
        className="rounded bg-editorial-ink-soft px-1.5 py-0.5 text-eyebrow text-editorial-ready"
        title={tooltipText}
      >
        ✓ auto-approved · {GATE_LABELS[gate] ?? gate}
      </span>
      {entry.rule_names.length > 0 && (
        <span
          className="text-eyebrow text-editorial-ivory-mute font-mono"
          title={tooltipText}
        >
          [{entry.rule_names.join(', ')}]
        </span>
      )}
      {onReject && (
        <button
          onClick={onReject}
          className="rounded border border-editorial-curtain/50 px-1.5 py-0.5 text-eyebrow text-editorial-curtain hover:bg-editorial-curtain/10"
          title="Override this auto-approve decision"
        >
          Reject
        </button>
      )}
    </div>
  )
}

export default AutoApproveBadge
