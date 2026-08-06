import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { GpuWorkerStatus, Project } from '../../types/project'
import { apiGet, apiPost } from '../../lib/api'
import { fileUrl } from '../../lib/mediaUrl'
import { Badge, Button, LiveRegion, LoadingState, MediaAsset } from '../ui'
import { GpuWorkersSection } from '../setup/inspector/GpuWorkersSection'

type MethodState = 'available' | 'canary' | 'blocked'
type ExperimentState =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'blocked'
  | 'unknown'
  | 'cancelled'

interface IdentityMethod {
  method: string
  label: string
  state: MethodState
  reason: string
  blocker_code?: string
  candidate_sha256?: string
}

interface IdentityCharacter {
  character_id: string
  name: string
  eligible: boolean
  reference_count: number
  reference_fingerprint: string
  references: Array<{
    role: string
    sha256: string
    size_bytes: number
    media_path: string
  }>
  reason: string
}

interface IdentityCell {
  cell_key: string
  method: string
  label: string
  reference_count: number
  seed: number
  state: string
  prompt_id: string | null
  output_path: string | null
  output_sha256: string | null
  latency_ms: number | null
  identity_score: number | null
  identity_verdict: string | null
  safe_error: string
}

interface IdentityExperiment {
  experiment_id: string
  character_id: string
  method: string
  state: ExperimentState
  cancel_requested: boolean
  lora_consent: boolean
  safe_error: string
  created_at: number | string
  updated_at: number | string
  references: Array<{ role: string; sha256: string; size_bytes: number }>
  reference_count: number
  cells: IdentityCell[]
}

interface IdentityExperimentList {
  experiments: IdentityExperiment[]
  methods: IdentityMethod[]
  characters: IdentityCharacter[]
  prompt: string
}

interface Props {
  project: Project
  apiBase: string
}

const RUNNING_STATES = new Set<ExperimentState>(['queued', 'running'])
const BLOCKING_STATES = new Set<ExperimentState>(['queued', 'running', 'unknown'])
const RESUMABLE_STATES = new Set<ExperimentState>(['failed', 'blocked', 'unknown'])
const POLL_MS = 1000

function experimentTime(value: number | string): string {
  const date = new Date(typeof value === 'number' ? value * 1000 : value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

function requestId(): string {
  const uuid = globalThis.crypto?.randomUUID?.()
  if (uuid) return uuid.replace(/-/g, '').toLowerCase()
  return `identity-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function upsertExperiment(
  experiments: IdentityExperiment[],
  next: IdentityExperiment,
): IdentityExperiment[] {
  return [next, ...experiments.filter((item) => item.experiment_id !== next.experiment_id)]
}

function scoreLabel(score: number | null): string {
  return score === null ? 'UNKNOWN' : score.toFixed(3)
}

function verdictLabel(verdict: string | null): string {
  return verdict ? verdict.toUpperCase() : 'UNKNOWN'
}

export default function IdentityLabPage({ project, apiBase }: Props) {
  const base = (apiBase || '/api').replace(/\/$/, '')
  const endpoint = `${base}/projects/${encodeURIComponent(project.id)}/identity-experiments`
  const [catalog, setCatalog] = useState<IdentityExperimentList | null>(null)
  const [selectedCharacterId, setSelectedCharacterId] = useState('')
  const [selected, setSelected] = useState<IdentityExperiment | null>(null)
  const [imageWorker, setImageWorker] = useState<GpuWorkerStatus | null>(null)
  const [loraConsentFingerprint, setLoraConsentFingerprint] = useState('')
  const [loading, setLoading] = useState(true)
  const [mutating, setMutating] = useState(false)
  const [error, setError] = useState('')
  const [announcement, setAnnouncement] = useState('')
  const pendingRequestIds = useRef(new Map<string, string>())

  const loadList = useCallback(async () => {
    setLoading(true)
    setError('')
    const result = await apiGet<IdentityExperimentList>(endpoint)
    if (!result.ok) {
      setError(result.error)
      setLoading(false)
      return
    }
    setCatalog(result.data)
    setSelectedCharacterId((current) => (
      result.data.characters.some((character) => character.character_id === current)
        ? current
        : result.data.characters.find((character) => character.eligible)?.character_id
          ?? result.data.characters[0]?.character_id
          ?? ''
    ))
    setSelected((current) => {
      if (current) {
        return result.data.experiments.find(
          (experiment) => experiment.experiment_id === current.experiment_id,
        ) ?? current
      }
      return result.data.experiments[0] ?? null
    })
    setLoading(false)
  }, [endpoint])

  useEffect(() => {
    void loadList()
  }, [loadList])

  useEffect(() => {
    if (!selected || !RUNNING_STATES.has(selected.state)) return
    let stopped = false
    let timer: number | undefined

    const poll = async () => {
      const result = await apiGet<IdentityExperiment>(
        `${endpoint}/${encodeURIComponent(selected.experiment_id)}`,
      )
      if (stopped) return
      if (!result.ok) {
        setError(result.error)
        timer = window.setTimeout(() => void poll(), POLL_MS)
        return
      }
      setError('')
      setSelected(result.data)
      setCatalog((current) => current
        ? { ...current, experiments: upsertExperiment(current.experiments, result.data) }
        : current)
      setAnnouncement(`Identity comparison ${result.data.state}.`)
      if (RUNNING_STATES.has(result.data.state)) {
        timer = window.setTimeout(() => void poll(), POLL_MS)
      }
    }

    timer = window.setTimeout(() => void poll(), POLL_MS)
    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [endpoint, selected?.experiment_id, selected?.state])

  const selectedCharacter = catalog?.characters.find(
    (character) => character.character_id === selectedCharacterId,
  ) ?? null
  const loraConsent = selectedCharacterId !== ''
    && selectedCharacter?.reference_fingerprint !== ''
    && loraConsentFingerprint === selectedCharacter?.reference_fingerprint
  const nativeMethod = catalog?.methods.find((method) => method.method === 'native_flux2') ?? null
  const loraMethod = catalog?.methods.find(
    (method) => method.method === 'flux2_character_lora',
  ) ?? null
  const activeExperiment = catalog?.experiments.find((experiment) => (
    BLOCKING_STATES.has(experiment.state)
  )) ?? null
  const workerReady = imageWorker?.state === 'ready'
    && imageWorker.startup_ready === true
    && imageWorker.execution_proven === true
    && imageWorker.benchmark_state === 'passed'
  const loraRunnable = loraMethod?.state === 'available' || loraMethod?.state === 'canary'
  const canRun = Boolean(
    selectedCharacter?.eligible
    && nativeMethod?.state === 'available'
    && loraRunnable
    && workerReady
    && loraConsent
    && !activeExperiment
    && !mutating,
  )

  const comparisonUnavailableReason = useMemo(() => {
    if (!nativeMethod) return 'Native FLUX.2 is not available.'
    if (nativeMethod.state !== 'available') return nativeMethod.reason
    if (!loraMethod) return 'Character LoRA is not available.'
    if (!loraRunnable) return loraMethod.reason
    if (!selectedCharacter) return 'Select a character.'
    if (!selectedCharacter.eligible) return selectedCharacter.reason
    if (!workerReady) return 'The image worker must be Ready with startup, execution, and benchmark proof.'
    if (activeExperiment) return 'Resolve the active identity comparison before starting another.'
    if (!loraConsent) return 'Confirm authorized use of the four identity references for local LoRA training.'
    return ''
  }, [activeExperiment, loraConsent, loraMethod, loraRunnable, nativeMethod, selectedCharacter, workerReady])

  const updateExperiment = (experiment: IdentityExperiment) => {
    setSelected(experiment)
    setCatalog((current) => current
      ? { ...current, experiments: upsertExperiment(current.experiments, experiment) }
      : current)
  }

  const createExperiment = async () => {
    if (!canRun || !selectedCharacter) return
    setMutating(true)
    setError('')
    const retryKey = pendingRequestIds.current.get(selectedCharacter.character_id) ?? requestId()
    pendingRequestIds.current.set(selectedCharacter.character_id, retryKey)
    const result = await apiPost<IdentityExperiment>(endpoint, {
      character_id: selectedCharacter.character_id,
      request_id: retryKey,
      lora_consent: true,
      reference_fingerprint: selectedCharacter.reference_fingerprint,
    })
    setMutating(false)
    if (!result.ok) {
      setError(result.error)
      setAnnouncement('Identity comparison was not queued.')
      return
    }
    pendingRequestIds.current.delete(selectedCharacter.character_id)
    updateExperiment(result.data)
    setLoraConsentFingerprint('')
    setAnnouncement('Identity comparison queued.')
  }

  const mutateExperiment = async (action: 'cancel' | 'resume') => {
    if (!selected || mutating) return
    setMutating(true)
    setError('')
    const result = await apiPost<IdentityExperiment>(
      `${endpoint}/${encodeURIComponent(selected.experiment_id)}/${action}`,
      {},
    )
    setMutating(false)
    if (!result.ok) {
      setError(result.error)
      setAnnouncement(`Identity comparison ${action} failed.`)
      return
    }
    updateExperiment(result.data)
    setAnnouncement(action === 'cancel'
      ? 'Identity comparison cancellation requested.'
      : 'Identity comparison queued to resume.')
  }

  const selectHistory = async (experiment: IdentityExperiment) => {
    setSelected(experiment)
    const result = await apiGet<IdentityExperiment>(
      `${endpoint}/${encodeURIComponent(experiment.experiment_id)}`,
    )
    if (result.ok) updateExperiment(result.data)
  }

  return (
    <div data-page="identity" className="flex h-full min-h-0 bg-app text-tx">
      <aside className="w-[300px] shrink-0 overflow-y-auto border-r border-line bg-gutter">
        <div className="border-b border-line px-3 py-3">
          <p className="font-mono text-[10px] uppercase tracking-wide text-mut">Identity Lab</p>
          <h1 className="mt-1 font-display-headline text-xl">Identity comparison</h1>
          <p className="mt-2 text-[11px] leading-4 text-mut">
            Compare native one, two, and four-reference generation against text-only and character-LoRA arms.
          </p>
        </div>
        <GpuWorkersSection onImageWorker={setImageWorker} />
        <section className="px-3 py-3" aria-labelledby="identity-history-heading">
          <h2 id="identity-history-heading" className="font-mono text-[10px] uppercase tracking-wide text-mut">
            History
          </h2>
          {catalog?.experiments.length ? (
            <ul className="mt-2 space-y-1">
              {catalog.experiments.map((experiment) => {
                const active = selected?.experiment_id === experiment.experiment_id
                const character = catalog.characters.find(
                  (item) => item.character_id === experiment.character_id,
                )
                return (
                  <li key={experiment.experiment_id}>
                    <button
                      type="button"
                      onClick={() => void selectHistory(experiment)}
                      aria-current={active ? 'true' : undefined}
                      className={`w-full rounded border px-2 py-2 text-left ${
                        active ? 'border-acc bg-acc-dim' : 'border-line bg-panel hover:border-acc/60'
                      }`}
                    >
                      <span className="block truncate text-[11px] text-tx">
                        {character?.name ?? experiment.character_id}
                      </span>
                      <span className="mt-1 flex items-center justify-between gap-2 font-mono text-[9px] uppercase tracking-wide text-mut">
                        <span>{experimentTime(experiment.created_at)}</span>
                        <span>{experiment.state}</span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="mt-2 text-[10px] text-mut">No comparisons yet.</p>
          )}
        </section>
      </aside>

      <div className="min-w-0 flex-1 overflow-y-auto px-5 py-4">
        <LiveRegion message={announcement} />
        {error && (
          <p role="alert" className="mb-3 rounded border border-fail/50 bg-fail/[0.04] px-3 py-2 text-[11px] text-fail">
            {error}
          </p>
        )}
        {loading && !catalog ? (
          <LoadingState label="Loading Identity Lab" />
        ) : catalog ? (
          <>
            <section aria-labelledby="identity-methods-heading">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 id="identity-methods-heading" className="font-display-headline text-2xl">Methods</h2>
                  <p className="mt-1 max-w-3xl text-[11px] leading-4 text-mut">{catalog.prompt}</p>
                </div>
                <label className="text-[10px] text-mut">
                  <span className="mb-1 block font-mono uppercase tracking-wide">Character</span>
                  <select
                    value={selectedCharacterId}
                    onChange={(event) => {
                      setSelectedCharacterId(event.target.value)
                      setLoraConsentFingerprint('')
                    }}
                    className="min-w-48 rounded border border-line bg-panel px-2 py-1.5 text-[11px] text-tx"
                  >
                    {catalog.characters.length === 0 && <option value="">No characters</option>}
                    {catalog.characters.map((character) => (
                      <option key={character.character_id} value={character.character_id}>
                        {character.name} · {character.reference_count}/4 refs
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                {catalog.methods.map((method) => {
                  const native = method.method === 'native_flux2'
                  const lora = method.method === 'flux2_character_lora'
                  const blocked = method.state === 'blocked'
                  const canary = method.state === 'canary'
                  return (
                    <article key={method.method} className="rounded border border-line bg-panel p-3">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-sm font-medium text-tx">{method.label}</h3>
                        <Badge variant={blocked ? 'fail' : canary ? 'warn' : workerReady ? 'ok' : 'warn'}>
                          {blocked ? 'Blocked' : canary ? 'Canary' : workerReady ? 'Ready' : 'Waiting'}
                        </Badge>
                      </div>
                      <p className="mt-2 min-h-8 text-[10px] leading-4 text-mut">
                        {blocked
                          ? method.reason
                          : lora
                            ? comparisonUnavailableReason || method.reason
                            : method.reason}
                      </p>
                      {native && !blocked && (
                        <p className="mt-3 rounded border border-line px-2 py-1.5 text-center font-mono text-[9px] uppercase tracking-wide text-mut">
                          Included in full comparison
                        </p>
                      )}
                      {lora && !blocked && (
                        <>
                          {selectedCharacter && selectedCharacter.references.length > 0 && (
                            <div className="mt-3 grid grid-cols-4 gap-1" aria-label="Selected LoRA training references">
                              {selectedCharacter.references.map((reference, index) => (
                                <div key={`${reference.role}-${reference.sha256}`} className="min-w-0">
                                  <img
                                    src={fileUrl(base, project.id, reference.media_path)}
                                    alt={`${reference.role} identity reference ${index + 1}`}
                                    className="aspect-square w-full rounded border border-line object-cover"
                                  />
                                  <p className="mt-1 truncate font-mono text-[8px] text-mut">
                                    {reference.role} · {reference.sha256.slice(0, 12)}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}
                          <label className="mt-3 flex items-start gap-2 text-[10px] leading-4 text-mut">
                            <input
                              type="checkbox"
                              checked={loraConsent}
                              onChange={(event) => setLoraConsentFingerprint(
                                event.target.checked ? selectedCharacter?.reference_fingerprint ?? '' : '',
                              )}
                              className="mt-0.5"
                            />
                            <span>I confirm authorized local training use of these four identity references.</span>
                          </label>
                          <Button
                            size="sm"
                            fullWidth
                            className="mt-3"
                            disabled={!canRun}
                            isLoading={mutating}
                            onClick={() => void createExperiment()}
                          >
                            Run native + LoRA comparison
                          </Button>
                        </>
                      )}
                      {!native && !lora && !blocked && (
                        <Button size="sm" fullWidth className="mt-3" disabled>
                          Unavailable
                        </Button>
                      )}
                      {blocked && (
                        <Button size="sm" fullWidth className="mt-3" disabled>
                          Unavailable
                        </Button>
                      )}
                    </article>
                  )
                })}
              </div>
            </section>

            <section className="mt-5" aria-labelledby="identity-results-heading">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 id="identity-results-heading" className="font-display-headline text-2xl">Results</h2>
                  {selected && (
                    <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-mut">
                      {selected.state} · {selected.reference_count} approved references
                    </p>
                  )}
                </div>
                {selected && (
                  <div className="flex gap-2">
                    {RUNNING_STATES.has(selected.state) && (
                      <Button
                        variant="curtain-outline"
                        size="sm"
                        disabled={mutating || selected.cancel_requested}
                        onClick={() => void mutateExperiment('cancel')}
                      >
                        {selected.cancel_requested ? 'Cancel requested' : 'Cancel'}
                      </Button>
                    )}
                    {RESUMABLE_STATES.has(selected.state) && (
                      <Button
                        variant="brass-outline"
                        size="sm"
                        disabled={
                          mutating
                          || Boolean(
                            activeExperiment
                            && activeExperiment.experiment_id !== selected.experiment_id,
                          )
                        }
                        onClick={() => void mutateExperiment('resume')}
                      >
                        Resume
                      </Button>
                    )}
                  </div>
                )}
              </div>

              {!selected ? (
                <p className="mt-3 rounded border border-line bg-panel px-3 py-6 text-center text-[11px] text-mut">
                  Run a comparison or choose one from history.
                </p>
              ) : (
                <>
                  {selected.safe_error && (
                    <p role="alert" className="mt-3 rounded border border-fail/50 px-3 py-2 text-[11px] text-fail">
                      {selected.safe_error}
                    </p>
                  )}
                  <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                    {[...selected.cells]
                      .map((cell) => (
                        <article key={cell.cell_key} className="overflow-hidden rounded border border-line bg-panel">
                          <div className="flex items-center justify-between px-3 py-2">
                            <h3 className="font-mono text-[11px] uppercase tracking-wide text-tx">
                              {cell.label || (
                                `${cell.reference_count} ${cell.reference_count === 1 ? 'reference' : 'references'}`
                              )}
                            </h3>
                            <Badge variant={cell.state === 'succeeded' ? 'ok' : cell.state === 'running' ? 'warn' : 'neutral'}>
                              {cell.state}
                            </Badge>
                          </div>
                          <MediaAsset
                            kind="image"
                            url={cell.output_path
                              ? fileUrl(base, project.id, cell.output_path)
                              : null}
                            alt={`${cell.label || `${cell.reference_count}-reference`} identity comparison`}
                            emptyLabel={cell.state === 'running' ? 'Generating' : 'No result yet'}
                            className="aspect-square border-y border-line"
                            objectFit="contain"
                          />
                          <dl className="grid grid-cols-2 gap-2 px-3 py-3 text-[10px]">
                            <div>
                              <dt className="font-mono uppercase tracking-wide text-mut">Score</dt>
                              <dd className="mt-0.5 text-tx">{scoreLabel(cell.identity_score)}</dd>
                            </div>
                            <div>
                              <dt className="font-mono uppercase tracking-wide text-mut">Verdict</dt>
                              <dd className="mt-0.5 text-tx">{verdictLabel(cell.identity_verdict)}</dd>
                            </div>
                            <div>
                              <dt className="font-mono uppercase tracking-wide text-mut">Seed</dt>
                              <dd className="mt-0.5 text-tx">{cell.seed}</dd>
                            </div>
                            <div>
                              <dt className="font-mono uppercase tracking-wide text-mut">Latency</dt>
                              <dd className="mt-0.5 text-tx">
                                {cell.latency_ms === null ? 'UNKNOWN' : `${cell.latency_ms} ms`}
                              </dd>
                            </div>
                          </dl>
                          {cell.safe_error && (
                            <p className="border-t border-line px-3 py-2 text-[10px] leading-4 text-fail">
                              {cell.safe_error}
                            </p>
                          )}
                        </article>
                      ))}
                  </div>
                </>
              )}
            </section>
          </>
        ) : null}
      </div>
    </div>
  )
}
