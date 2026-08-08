/**
 * Reference Sheet — the page that makes the identity lever visible.
 *
 * This is a cinema pipeline: every still exists to become a shot, and video
 * models COPY identity from the references they are handed rather than
 * inventing it. The reference SET is therefore the quality lever, and until
 * this page existed nothing in the product showed what was in it.
 *
 * Three things this page refuses to do, each for a measured reason:
 *
 * 1. IT SHOWS NO IDENTITY SCORE. ADR-092: the scorer inverts rank off-angle. A
 *    real photograph of the subject in profile scored 0.556 and "failed" the
 *    0.70 gate, while a generated panel the subject confirmed was NOT him
 *    scored 0.570. A number that ranks a stranger above the subject is worse
 *    than no number, because it looks authoritative. Provenance is shown
 *    instead — it is a fact about where the image came from, not an estimate.
 *
 * 2. IT DOES NOT PRETEND EVERY REFERENCE IS USED. Every consumer truncates the
 *    set from the front at a DIFFERENT cut — 1 for Kling's frontal slot, 4 on
 *    the fal/Veo path, 6 through Kontext, 8 beside a Seedance keyframe. A user
 *    who uploads a tenth photograph and sees it in a grid reasonably concludes
 *    it is being used. The delivery strip says otherwise, per provider.
 *
 * 3. IT DOES NOT TREAT ORDER AS COSMETIC. Slot 0 is uploaded as Kling's FRONTAL
 *    image. On this project it was a left profile, so Kling was told a profile
 *    was the frontal view. Reordering here is a generation change, not a
 *    display preference, so it is saved explicitly rather than live.
 */

import { useCallback, useMemo, useState } from 'react'
import type {
  Character,
  IdentityReference,
  Project,
  ReferenceCoverage,
  ReferenceDelivery,
  ReferenceOrigin,
} from '../../types/project'
import { apiRequest } from '../../lib/api'
import { fileUrl } from '../../lib/mediaUrl'
import { Badge, Button, EmptyState, LiveRegion, MICRO_LABEL } from '../ui'

interface Props {
  project: Project
  apiBase?: string
  onRefresh?: () => void
}

/** Where each provider stops reading, measured from the code that slices.
 *  Keep these in step with the cited call sites — a stale cut here would be a
 *  confident lie about what reaches a model. */
export const DELIVERY_CUTS: { label: string; cut: number; where: string }[] = [
  { label: 'Kling frontal', cut: 1, where: 'phase_c_ffmpeg.py:2245 uploads ref 0 as the frontal image' },
  { label: 'Veo / fal', cut: 4, where: 'phase_c_ffmpeg.py:2122 slices [:4]' },
  { label: 'Kontext', cut: 6, where: 'phase_c_assembly.py:1112 slices [:6]' },
  { label: 'Gemini', cut: 8, where: 'gemini_image_native.py:49 budget of 8' },
  { label: 'Seedance + keyframe', cut: 8, where: 'phase_c_ffmpeg.py:2428 slices [:8]; the keyframe is the 9th' },
]

const WIDEST_CUT = DELIVERY_CUTS.reduce((max, entry) => Math.max(max, entry.cut), 0)

const ORIGIN_LABEL: Record<ReferenceOrigin, string> = {
  photo: 'Photograph',
  defined: 'Defines this character',
  derived: 'Derived',
  invented: 'Invented',
  unknown: 'Unrecorded',
}

const ORIGIN_MEANING: Record<ReferenceOrigin, string> = {
  photo: 'A real photograph of the subject.',
  defined: 'The first generated image of a described character. There is nothing earlier for it to be faithful to — it IS the character.',
  derived: 'Generated from a source that contained this geometry, so the subject survived and only the lighting or expression changed.',
  invented: 'Generated from a source that did NOT contain this geometry. The model had no information and produced a plausible stranger. Feeding this to a video model teaches it the wrong face.',
  unknown: 'Migrated from before provenance was recorded. Its source cannot be established from the record.',
}

const ORIGIN_TONE: Record<ReferenceOrigin, 'ok' | 'warn' | 'fail' | 'neutral'> = {
  photo: 'ok',
  defined: 'ok',
  derived: 'neutral',
  invented: 'fail',
  unknown: 'warn',
}

const FACET_AXES = ['yaw', 'expression', 'light', 'framing'] as const

function originOf(reference: IdentityReference): ReferenceOrigin {
  const value = reference.origin
  return value in ORIGIN_LABEL ? value : 'unknown'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Move one entry, returning a NEW array. Out-of-range targets are no-ops so a
 *  double-click on the top item cannot silently wrap it to the bottom. */
export function moveReference<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) {
    return items
  }
  const next = items.slice()
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

/** Which references sit past EVERY provider's cut. These reach nothing at all,
 *  and saying so is the whole point of the delivery strip. */
export function referencesPastEveryCut(references: IdentityReference[]): IdentityReference[] {
  const kept = references.filter(reference => reference.judged !== 'reject')
  return kept.slice(WIDEST_CUT)
}

export default function ReferenceSheetPage({ project, apiBase, onRefresh }: Props) {
  const characters = project.characters ?? []
  const [selectedId, setSelectedId] = useState<string>(characters[0]?.id ?? '')
  const character: Character | undefined =
    characters.find(entry => entry.id === selectedId) ?? characters[0]

  const persisted = useMemo<IdentityReference[]>(
    () => (character?.identity_refs ?? []).filter(reference => Boolean(reference?.path)),
    [character],
  )
  /** Local working order. `null` means "no unsaved change" — the distinction
   *  matters because a reorder is a generation change and must be saved
   *  deliberately, not applied the moment an arrow is clicked. */
  const [draft, setDraft] = useState<IdentityReference[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [delivered, setDelivered] = useState<ReferenceDelivery | null>(null)
  const [coverage, setCoverage] = useState<ReferenceCoverage | null>(null)

  const references = draft ?? persisted
  const dirty = draft !== null

  const selectCharacter = useCallback((id: string) => {
    setSelectedId(id)
    setDraft(null)
    setDelivered(null)
    setCoverage(null)
    setMessage('')
    setError('')
  }, [])

  const save = useCallback(
    async (options: { reorderForCoverage?: boolean; canonical?: string } = {}) => {
      if (!character) return
      setBusy(true)
      setError('')
      setMessage('')
      const result = await apiRequest<unknown>(
        `/api/projects/${project.id}/characters/${character.id}/references`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            // `order` is its own field, and total. The route refuses anything
            // that is not an exact permutation, so a reorder can neither drop a
            // reference by omission nor invent one — and a facet patch that
            // happens to list fewer entries cannot reorder by accident.
            order: references.map(reference => reference.path),
            ...(options.canonical ? { canonical: options.canonical } : {}),
            references: references.map(reference => ({
              path: reference.path,
              yaw: reference.yaw,
              expression: reference.expression,
              light: reference.light,
              framing: reference.framing,
              origin: reference.origin,
              source_path: reference.source_path,
              judged: reference.judged,
              reason: reference.reason,
            })),
            reorder_for_coverage: Boolean(options.reorderForCoverage),
          }),
        },
      )
      setBusy(false)
      if (!result.ok) {
        setError(result.error)
        return
      }
      const body = isRecord(result.data) ? result.data : {}
      if (Array.isArray(body.identity_refs)) {
        setDraft(null)
      }
      if (isRecord(body.delivered)) {
        setDelivered(body.delivered as unknown as ReferenceDelivery)
      }
      if (isRecord(body.coverage)) {
        setCoverage(body.coverage as ReferenceCoverage)
      }
      setMessage(
        options.canonical
          ? 'Canonical changed. It now leads every provider set and is what identity validation compares against.'
          : options.reorderForCoverage
            ? 'Reordered for coverage and saved. Providers will read the new order.'
            : 'Saved. Providers will read the new order.',
      )
      onRefresh?.()
    },
    [character, project.id, references, onRefresh],
  )

  if (characters.length === 0) {
    return (
      <div className="p-6">
        <EmptyState
          title="No characters yet"
          message="A reference sheet describes one character's images. Create a character on the Setup page first."
        />
      </div>
    )
  }

  const kept = references.filter(reference => reference.judged !== 'reject')
  const orphans = referencesPastEveryCut(references)
  const invented = kept.filter(reference => originOf(reference) === 'invented')

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto bg-app p-6 text-tx">
      <LiveRegion message={message || error} />

      {/* ── Who ─────────────────────────────────────────────── */}
      <header className="mb-5 flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-[13px] uppercase tracking-[0.09em]">
          Reference sheet
        </h1>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Characters">
          {characters.map(entry => (
            <button
              key={entry.id}
              role="tab"
              aria-selected={entry.id === character?.id}
              onClick={() => selectCharacter(entry.id)}
              className={[
                'rounded px-3 py-1 font-mono text-[11px] uppercase tracking-wide transition-colors',
                entry.id === character?.id
                  ? 'bg-acc-dim text-white'
                  : 'text-mut hover:text-tx',
              ].join(' ')}
            >
              {entry.name || entry.id}
            </button>
          ))}
        </div>
        {character?.creation_kind === 'described' && (
          <Badge variant="cloud">Described character</Badge>
        )}
      </header>

      {/* ── What actually reaches a model ───────────────────── */}
      <section className="mb-6 rounded border border-line p-4">
        <h2 className={MICRO_LABEL}>Delivery — what each provider receives</h2>
        <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-mut">
          Every provider truncates this set from the front, each at a different
          cut. Position is the only thing that decides what survives.
        </p>

        <ol className="mt-3 flex flex-wrap gap-2" aria-label="Reference slots in delivery order">
          {kept.map((reference, index) => {
            const reached = DELIVERY_CUTS.filter(entry => index < entry.cut)
            const orphaned = reached.length === 0
            return (
              <li
                key={reference.path}
                className={[
                  'w-[104px] rounded border p-1',
                  orphaned ? 'border-line opacity-40' : 'border-line',
                ].join(' ')}
              >
                <img
                  src={fileUrl(apiBase, project.id, reference.path)}
                  alt={`Slot ${index}: ${reference.yaw}, ${reference.expression}`}
                  className="h-[72px] w-full rounded-sm object-cover"
                />
                <div className={`${MICRO_LABEL} mt-1`}>
                  slot {index}
                  {index === 0 && <span className="text-acc"> · frontal</span>}
                </div>
                <div className="font-mono text-[9px] leading-tight text-mut">
                  {orphaned ? 'reaches nothing' : reached.map(entry => entry.label).join(', ')}
                </div>
              </li>
            )
          })}
        </ol>

        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
          {DELIVERY_CUTS.map(entry => (
            <div key={`${entry.label}-${entry.cut}`} className="flex items-baseline gap-2">
              <dt className="font-mono text-[11px] text-tx">{entry.label}</dt>
              <dd className="font-mono text-[11px] text-mut">
                first {entry.cut} of {kept.length}
                {kept.length > entry.cut && (
                  <span className="text-warn"> · {kept.length - entry.cut} dropped</span>
                )}
              </dd>
            </div>
          ))}
        </dl>

        {orphans.length > 0 && (
          <p className="mt-3 rounded border border-warn/40 bg-warn/5 p-2 text-[12px] leading-relaxed text-tx">
            <strong className="font-mono text-[11px] uppercase tracking-wide">
              {orphans.length} reference{orphans.length === 1 ? '' : 's'} past every cut.
            </strong>{' '}
            Nothing reads them. Move one up to give it to a provider, or leave it
            as an archive — but it is not improving any render where it sits.
          </p>
        )}

        {delivered && (
          <p className={`${MICRO_LABEL} mt-2`}>
            Server confirmed: Kling frontal ={' '}
            {delivered.kling_frontal ? delivered.kling_frontal.split('/').pop() : 'none'}
          </p>
        )}
      </section>

      {/* ── Coverage ────────────────────────────────────────── */}
      <section className="mb-6 rounded border border-line p-4">
        <h2 className={MICRO_LABEL}>Coverage</h2>
        <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-mut">
          What the set SHOWS, per axis. A gap is a pose a video model will have
          to invent, which is the moment identity drifts.
        </p>
        <dl className="mt-2 space-y-1">
          {FACET_AXES.map(axis => {
            const counts =
              coverage?.[axis]
              ?? kept.reduce<Record<string, number>>((totals, reference) => {
                const value = String(reference[axis] ?? 'unknown')
                totals[value] = (totals[value] ?? 0) + 1
                return totals
              }, {})
            const entries = Object.entries(counts)
            return (
              <div key={axis} className="flex flex-wrap items-baseline gap-2">
                <dt className="w-24 font-mono text-[11px] uppercase tracking-wide text-mut">
                  {axis}
                </dt>
                <dd className="flex flex-wrap gap-2 font-mono text-[11px]">
                  {entries.length === 0 && <span className="text-mut">—</span>}
                  {entries.map(([value, count]) => (
                    <span
                      key={value}
                      className={count === 0 ? 'text-mut line-through' : 'text-tx'}
                    >
                      {value} {count}
                    </span>
                  ))}
                </dd>
              </div>
            )
          })}
        </dl>
      </section>

      {/* ── The set ─────────────────────────────────────────── */}
      <section className="rounded border border-line p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h2 className={MICRO_LABEL}>The set</h2>
          <span className="flex-1" />
          <Button
            variant="rule-only"
            size="sm"
            disabled={busy || references.length === 0}
            onClick={() => save({ reorderForCoverage: true })}
          >
            Order for coverage
          </Button>
          <Button
            variant="brass"
            size="sm"
            disabled={busy || !dirty}
            onClick={() => save()}
          >
            {dirty ? 'Save order' : 'Saved'}
          </Button>
        </div>

        {invented.length > 0 && (
          <p className="mb-3 rounded border border-fail/40 bg-fail/5 p-2 text-[12px] leading-relaxed text-tx">
            <strong className="font-mono text-[11px] uppercase tracking-wide">
              {invented.length} invented reference{invented.length === 1 ? '' : 's'} in use.
            </strong>{' '}
            Each was generated from a source that did not contain the pose it
            claims to show, so the model had nothing to work from and produced a
            plausible stranger. This is measured, not theoretical: the subject
            rejected exactly such a panel, and it had scored HIGHER than the one
            that was him. Reject it, or photograph that angle.
          </p>
        )}

        <ol className="space-y-2">
          {references.map((reference, index) => {
            const origin = originOf(reference)
            const rejected = reference.judged === 'reject'
            return (
              <li
                key={reference.path}
                className={[
                  'flex gap-3 rounded border p-2',
                  rejected ? 'border-line opacity-50' : 'border-line',
                ].join(' ')}
              >
                <img
                  src={fileUrl(apiBase, project.id, reference.path)}
                  alt={reference.path.split('/').pop() ?? reference.path}
                  className="h-[88px] w-[88px] flex-none rounded object-cover"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={MICRO_LABEL}>slot {index}</span>
                    {reference.roles?.includes('canonical') && (
                      <Badge variant="pri">Canonical</Badge>
                    )}
                    <Badge variant={ORIGIN_TONE[origin]}>{ORIGIN_LABEL[origin]}</Badge>
                    {rejected && <Badge variant="neutral">Rejected</Badge>}
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-mut">
                    {FACET_AXES.map(axis => String(reference[axis] ?? 'unknown')).join(' · ')}
                  </p>
                  <p className="mt-1 max-w-2xl text-[11px] leading-relaxed text-mut">
                    {ORIGIN_MEANING[origin]}
                    {reference.source_path && (
                      <> Source: <code>{reference.source_path.split('/').pop()}</code>.</>
                    )}
                  </p>
                </div>
                <div className="flex flex-none flex-col gap-1">
                  <button
                    aria-label={`Move slot ${index} earlier`}
                    disabled={index === 0}
                    onClick={() => setDraft(moveReference(references, index, index - 1))}
                    className="rounded border border-line px-2 py-0.5 font-mono text-[11px] text-mut hover:text-tx disabled:opacity-30"
                  >
                    ↑
                  </button>
                  <button
                    aria-label={`Move slot ${index} later`}
                    disabled={index === references.length - 1}
                    onClick={() => setDraft(moveReference(references, index, index + 1))}
                    className="rounded border border-line px-2 py-0.5 font-mono text-[11px] text-mut hover:text-tx disabled:opacity-30"
                  >
                    ↓
                  </button>
                  <button
                    aria-label={`Make slot ${index} the canonical`}
                    disabled={busy || reference.roles?.includes('canonical') || rejected}
                    title={
                      'The canonical leads every provider set AND is what identity '
                      + 'validation compares each frame against. A turned view here '
                      + 'will floor that check (ADR-092), so prefer a front close-up.'
                    }
                    onClick={() => save({ canonical: reference.path })}
                    className="rounded border border-line px-2 py-0.5 font-mono text-[10px] uppercase text-mut hover:text-tx disabled:opacity-30"
                  >
                    Canonical
                  </button>
                  <button
                    aria-label={rejected ? `Use ${reference.path}` : `Reject ${reference.path}`}
                    onClick={() =>
                      setDraft(
                        references.map((entry, position) =>
                          position === index
                            ? { ...entry, judged: rejected ? 'keep' : 'reject' }
                            : entry,
                        ),
                      )
                    }
                    className="rounded border border-line px-2 py-0.5 font-mono text-[10px] uppercase text-mut hover:text-tx"
                  >
                    {rejected ? 'Use' : 'Reject'}
                  </button>
                </div>
              </li>
            )
          })}
        </ol>

        {references.length === 0 && (
          <p className="text-[12px] text-mut">
            This character has no references. Every video provider will invent a
            face for it.
          </p>
        )}

        {error && (
          <p className="mt-3 font-mono text-[11px] text-fail" role="alert">
            {error}
          </p>
        )}
      </section>
    </div>
  )
}
