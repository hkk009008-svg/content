/**
 * PostRunSummary — modal aggregating auto-approve audit decisions across all shots.
 *
 * Triggered by the pipeline-completion SSE event (stage: "DONE") from the parent
 * component (EditorialShell). Auto-opens on run completion; dismissable; parent
 * should provide a re-open button so the user can revisit after closing.
 *
 * Displays:
 *   - Per-gate counts (plan / image / motion / final): N approved / M vetoed
 *     Motion gate only appears when at least one motion audit entry exists
 *     (opt-in per S12 / ADR-014).
 *   - Top-5 firing rules across all shots (by frequency)
 *   - List of all auto-approved takes with shot ID + gate + rules + reject affordance
 *
 * Each approved take row has a "Reject" button → opens RejectAutoApproveModal.
 */

import { useState, useMemo } from 'react'
import type { Project, AutoApproveAuditEntry } from '../../types/project'
import RejectAutoApproveModal from './RejectAutoApproveModal'

interface Props {
  project: Project
  isOpen: boolean
  onClose: () => void
  /** Called after a successful rejection so the parent can refresh project state. */
  onRejectSuccess?: () => void
  apiBase?: string
}

type Gate = 'plan' | 'image' | 'motion' | 'final'
const GATE_ORDER: Gate[] = ['plan', 'image', 'motion', 'final']
const GATE_LABELS: Record<Gate, string> = {
  plan: 'Plan',
  image: 'Image',
  motion: 'Motion',
  final: 'Final',
}

interface ApprovedRow {
  shotId: string
  gate: Gate
  entry: AutoApproveAuditEntry
}

interface GateStat {
  gate: Gate
  approved: number
  vetoed: number
}

export function PostRunSummary({
  project,
  isOpen,
  onClose,
  onRejectSuccess,
  apiBase = '/api',
}: Props) {
  const [rejectTarget, setRejectTarget] = useState<{ shotId: string; gate: Gate } | null>(null)

  // Aggregate audit entries across all shots in all scenes.
  const { gateStats, topRules, approvedRows, hasMotionEntries } = useMemo(() => {
    const allEntries: Array<{ shotId: string; entry: AutoApproveAuditEntry }> = []

    for (const scene of project.scenes) {
      for (const shot of scene.shots || []) {
        for (const entry of shot.auto_approve_audit || []) {
          allEntries.push({ shotId: shot.id, entry })
        }
      }
    }

    // Gate stats — count approved/vetoed per gate (most recent entry per gate per shot)
    const latestByGateAndShot = new Map<string, AutoApproveAuditEntry>()
    for (const { shotId, entry } of allEntries) {
      const key = `${shotId}::${entry.gate}`
      const existing = latestByGateAndShot.get(key)
      if (!existing || entry.timestamp > existing.timestamp) {
        latestByGateAndShot.set(key, entry)
      }
    }

    const gateCounts: Record<Gate, { approved: number; vetoed: number }> = {
      plan: { approved: 0, vetoed: 0 },
      image: { approved: 0, vetoed: 0 },
      motion: { approved: 0, vetoed: 0 },
      final: { approved: 0, vetoed: 0 },
    }
    let hasMotionEntries = false
    for (const [key, entry] of latestByGateAndShot) {
      const gate = entry.gate as Gate
      if (gate === 'motion') hasMotionEntries = true
      if (entry.auto_approved) {
        gateCounts[gate].approved++
      } else {
        gateCounts[gate].vetoed++
      }
    }

    const gateStats: GateStat[] = GATE_ORDER
      .filter(g => g !== 'motion' || hasMotionEntries)
      .map(g => ({ gate: g, approved: gateCounts[g].approved, vetoed: gateCounts[g].vetoed }))

    // Top-5 firing rules across all entries (frequency count)
    const ruleCounts = new Map<string, number>()
    for (const { entry } of allEntries) {
      for (const rule of entry.rule_names) {
        ruleCounts.set(rule, (ruleCounts.get(rule) ?? 0) + 1)
      }
    }
    const topRules = [...ruleCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([rule, count]) => ({ rule, count }))

    // Auto-approved rows for the "override" table — most-recent-per-gate per shot only
    const approvedRows: ApprovedRow[] = []
    for (const [key, entry] of latestByGateAndShot) {
      if (!entry.auto_approved) continue
      const [shotId] = key.split('::')
      approvedRows.push({ shotId, gate: entry.gate as Gate, entry })
    }
    // Sort chronologically (oldest first) for a readable audit trail
    approvedRows.sort((a, b) => (a.entry.timestamp < b.entry.timestamp ? -1 : 1))

    return { gateStats, topRules, approvedRows, hasMotionEntries }
  }, [project])

  if (!isOpen) return null

  const handleReject = (shotId: string, gate: Gate) => {
    setRejectTarget({ shotId, gate })
  }

  const handleRejectSubmit = () => {
    setRejectTarget(null)
    onRejectSuccess?.()
  }

  const totalApproved = gateStats.reduce((s, g) => s + g.approved, 0)
  const totalVetoed = gateStats.reduce((s, g) => s + g.vetoed, 0)

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-40 flex items-center justify-center bg-black/70"
        onClick={onClose}
        role="dialog"
        aria-modal="true"
        aria-label="Run auto-approve summary"
      >
        {/* Dialog panel */}
        <div
          className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-lg border border-editorial-rule bg-editorial-ink p-6 shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute mb-1">
                Run Complete
              </div>
              <h2 className="text-xl font-semibold text-editorial-ivory">
                Auto-Approve Summary
              </h2>
              <p className="mt-1.5 text-sm text-editorial-ivory-mute">
                {totalApproved} decision{totalApproved === 1 ? '' : 's'} auto-approved
                {totalVetoed > 0 && `, ${totalVetoed} vetoed`} across this run.
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-editorial-ivory-mute hover:text-editorial-ivory text-lg leading-none"
              aria-label="Close summary"
            >
              ×
            </button>
          </div>

          {/* Gate stats */}
          {gateStats.length > 0 ? (
            <section className="mb-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute mb-3">
                Per-Gate Results
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {gateStats.map(({ gate, approved, vetoed }) => (
                  <div
                    key={gate}
                    className="rounded border border-editorial-rule bg-editorial-ink-soft px-3 py-3"
                  >
                    <div className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute mb-2">
                      {GATE_LABELS[gate]}
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-lg font-mono text-editorial-ready">{approved}</span>
                      <span className="text-eyebrow text-editorial-ivory-mute">approved</span>
                    </div>
                    {vetoed > 0 && (
                      <div className="flex items-baseline gap-1.5 mt-1">
                        <span className="text-sm font-mono text-editorial-warn">{vetoed}</span>
                        <span className="text-eyebrow text-editorial-ivory-mute">vetoed</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          ) : (
            <div className="mb-6 rounded border border-editorial-rule bg-editorial-ink-soft px-4 py-6 text-center text-sm text-editorial-ivory-mute">
              No auto-approve entries found. Auto-approve may not be configured for this project.
            </div>
          )}

          {/* Top rules */}
          {topRules.length > 0 && (
            <section className="mb-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute mb-3">
                Top Firing Rules
              </div>
              <ul className="space-y-1.5">
                {topRules.map(({ rule, count }) => (
                  <li
                    key={rule}
                    className="flex items-center justify-between gap-3 rounded border border-editorial-rule bg-editorial-ink-soft px-3 py-2"
                  >
                    <span className="text-sm font-mono text-editorial-ivory">{rule}</span>
                    <span className="text-xs font-mono text-editorial-ivory-mute flex-shrink-0">
                      ×{count}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Approved decisions table with reject affordance */}
          {approvedRows.length > 0 && (
            <section>
              <div className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute mb-3">
                Auto-Approved Decisions — Override
              </div>
              <div className="space-y-2">
                {approvedRows.map(({ shotId, gate, entry }) => (
                  <div
                    key={`${shotId}::${gate}`}
                    className="flex items-center justify-between gap-3 rounded border border-editorial-rule bg-editorial-ink-soft px-3 py-2.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-mono text-editorial-brass">
                          {GATE_LABELS[gate]}
                        </span>
                        <span className="text-xs text-editorial-ivory-mute font-mono truncate">
                          {shotId}
                        </span>
                      </div>
                      {entry.rule_names.length > 0 && (
                        <div className="mt-0.5 text-eyebrow text-editorial-ivory-mute">
                          {entry.rule_names.join(', ')}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => handleReject(shotId, gate)}
                      className="flex-shrink-0 rounded border border-editorial-curtain/50 px-2.5 py-1 text-eyebrow text-editorial-curtain hover:bg-editorial-curtain/10"
                    >
                      Reject
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Footer */}
          <div className="mt-6 flex justify-end">
            <button
              onClick={onClose}
              className="rounded border border-editorial-rule px-4 py-2 text-sm text-editorial-ivory-mute hover:bg-editorial-ink-soft"
            >
              Close
            </button>
          </div>
        </div>
      </div>

      {/* Nested reject modal */}
      {rejectTarget && (
        <RejectAutoApproveModal
          projectId={project.id}
          shotId={rejectTarget.shotId}
          gate={rejectTarget.gate}
          isOpen={true}
          onClose={() => setRejectTarget(null)}
          onSubmit={handleRejectSubmit}
          apiBase={apiBase}
        />
      )}
    </>
  )
}

export default PostRunSummary
