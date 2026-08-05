import { useEffect, useRef, useState } from 'react'
import type {
  Project,
  AppConfig,
  LoraStatus,
  PendingCharacterCreation,
} from '../types/project'
import { apiDelete, apiPut, apiRequest, type ApiResult } from '../lib/api'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

const HISTORICAL_LORA_STATUSES = new Set([
  'idle',
  'preparing',
  'training',
  'validating',
  'done',
  'failed',
])

interface HistoricalLoraSummary {
  status: LoraStatus['status']
  qualityScore: number | null
  verdict: 'rejected' | 'warning' | 'recorded' | null
  artifactRecorded: boolean
  containsError: boolean
}

type HistoricalLoraLoad =
  | { kind: 'loading' }
  | { kind: 'ready'; summary: HistoricalLoraSummary }
  | { kind: 'error' }

const LOADING_LORA_STATUS: HistoricalLoraLoad = { kind: 'loading' }
const PENDING_CHARACTER_STATUSES = new Set([
  'submitting',
  'retryable',
  'reconciliation_required',
])

type PendingCreationLoad =
  | { kind: 'loading' }
  | { kind: 'ready'; pending: PendingCharacterCreation | null }
  | { kind: 'error' }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parsePendingCharacterCreation(value: unknown): PendingCharacterCreation | null {
  if (!isRecord(value)) return null
  if (
    typeof value.creation_request_id !== 'string'
    || !/^[0-9a-f]{32}$/.test(value.creation_request_id)
    || typeof value.name !== 'string'
    || value.name.length > 200
    || typeof value.status !== 'string'
    || !PENDING_CHARACTER_STATUSES.has(value.status)
    || typeof value.retryable !== 'boolean'
    || typeof value.message !== 'string'
    || value.message.length > 500
  ) return null
  for (const key of ['provider_job_id', 'attempt_state', 'created_at', 'updated_at']) {
    const field = value[key]
    if (field !== null && typeof field !== 'string') return null
  }
  return value as unknown as PendingCharacterCreation
}

function parsePendingCreationEnvelope(value: unknown): PendingCreationLoad {
  if (
    !isRecord(value)
    || !Object.prototype.hasOwnProperty.call(value, 'pending_creation')
  ) {
    return { kind: 'error' }
  }
  if (value.pending_creation === null) return { kind: 'ready', pending: null }
  const pending = parsePendingCharacterCreation(value.pending_creation)
  return pending ? { kind: 'ready', pending } : { kind: 'error' }
}

async function loadPendingCharacterCreation(projectId: string): Promise<PendingCreationLoad> {
  const result = await apiRequest<unknown>(
    `${API}/projects/${projectId}/characters/pending-creation`,
  )
  if (!result.ok) return { kind: 'error' }
  return parsePendingCreationEnvelope(result.data)
}

/** Validate the status fields this operator surface consumes, then discard
 * server-local path/error contents in favor of sanitized presence flags. */
function parseHistoricalLoraStatus(
  value: unknown,
  expectedCharacterId: string,
): HistoricalLoraSummary | null {
  if (!isRecord(value)) return null
  if (value.char_id !== expectedCharacterId) return null
  if (
    typeof value.status !== 'string'
    || !HISTORICAL_LORA_STATUSES.has(value.status)
  ) return null

  const loraPath = value.lora_path
  if (loraPath !== undefined && loraPath !== null && typeof loraPath !== 'string') {
    return null
  }
  const qualityScore = value.quality_score
  if (
    qualityScore !== undefined
    && qualityScore !== null
    && (typeof qualityScore !== 'number' || !Number.isFinite(qualityScore))
  ) return null
  const rejected = value.rejected
  if (rejected !== undefined && typeof rejected !== 'boolean') return null
  const qualityWarning = value.quality_warning
  if (qualityWarning !== undefined && typeof qualityWarning !== 'boolean') return null
  const error = value.error
  if (error !== undefined && error !== null && typeof error !== 'string') return null

  const normalizedScore = typeof qualityScore === 'number' ? qualityScore : null
  const verdict = rejected === true
    ? 'rejected'
    : qualityWarning === true
      ? 'warning'
      : normalizedScore !== null
        ? 'recorded'
        : null

  return {
    status: value.status,
    qualityScore: normalizedScore,
    verdict,
    artifactRecorded: typeof loraPath === 'string' && loraPath.trim().length > 0,
    containsError: typeof error === 'string' && error.trim().length > 0,
  }
}

function loraStatusRequestKey(projectId: string, characterId: string): string {
  return `${projectId}\u0000${characterId}`
}

function newCreationRequestId(): string {
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
}

async function loadHistoricalLoraStatus(
  projectId: string,
  characterId: string,
): Promise<HistoricalLoraLoad> {
  try {
    const response = await fetch(
      `${API}/projects/${projectId}/characters/${characterId}/lora-status`,
    )
    if (!response.ok) return { kind: 'error' }
    const parsed = parseHistoricalLoraStatus(await response.json(), characterId)
    return parsed ? { kind: 'ready', summary: parsed } : { kind: 'error' }
  } catch {
    return { kind: 'error' }
  }
}

export default function CharacterPanel({ project, config, onRefresh }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', description: '', voice_id: '' })
  const [files, setFiles] = useState<FileList | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [loraLoads, setLoraLoads] = useState<Record<string, HistoricalLoraLoad>>({})
  const loraRequests = useRef(new Map<string, Promise<HistoricalLoraLoad>>())
  const creationRequestId = useRef<string | null>(null)
  const [pendingCreationLoad, setPendingCreationLoad] = useState<PendingCreationLoad>(() => {
    if (project.pending_character_creation === null) {
      return { kind: 'ready', pending: null }
    }
    if (project.pending_character_creation !== undefined) {
      const pending = parsePendingCharacterCreation(project.pending_character_creation)
      return pending ? { kind: 'ready', pending } : { kind: 'error' }
    }
    return { kind: 'loading' }
  })
  const characterStatusKey = JSON.stringify(project.characters.map((c) => c.id))
  const embeddedPendingKey = JSON.stringify(project.pending_character_creation)

  useEffect(() => {
    let cancelled = false
    creationRequestId.current = null
    const embedded = project.pending_character_creation
    if (embedded === null) {
      setPendingCreationLoad({ kind: 'ready', pending: null })
      return () => { cancelled = true }
    }
    if (embedded !== undefined) {
      const pending = parsePendingCharacterCreation(embedded)
      setPendingCreationLoad(
        pending ? { kind: 'ready', pending } : { kind: 'error' },
      )
      return () => { cancelled = true }
    }
    setPendingCreationLoad({ kind: 'loading' })
    void loadPendingCharacterCreation(project.id).then((loaded) => {
      if (!cancelled) setPendingCreationLoad(loaded)
    })
    return () => { cancelled = true }
  }, [project.id, embeddedPendingKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const refreshPendingCreation = async (): Promise<PendingCreationLoad> => {
    const loaded = await loadPendingCharacterCreation(project.id)
    setPendingCreationLoad(loaded)
    return loaded
  }

  // One diagnostic GET per character. Even a legacy "training" state is
  // historical: dormant-policy fields can never restore an action or polling.
  useEffect(() => {
    let cancelled = false
    const requests = project.characters.map((character) => ({
      characterId: character.id,
      key: loraStatusRequestKey(project.id, character.id),
    }))

    if (requests.length > 0) {
      setLoraLoads((previous) => {
        const next = { ...previous }
        for (const { key } of requests) {
          if (!(key in next)) next[key] = LOADING_LORA_STATUS
        }
        return next
      })
    }

    for (const { characterId, key } of requests) {
      let request = loraRequests.current.get(key)
      if (!request) {
        request = loadHistoricalLoraStatus(project.id, characterId)
        loraRequests.current.set(key, request)
      }
      void request.then((result) => {
        if (!cancelled) {
          setLoraLoads((previous) => ({ ...previous, [key]: result }))
        }
      })
    }

    return () => { cancelled = true }
  }, [project.id, characterStatusKey]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Shared truthfulness plumbing for every character mutation here — the
   *  same check-then-refresh-or-surface shape ShotInspector's `runMutation`
   *  uses for the sibling shot/character/project PUTs. A non-2xx or network
   *  failure surfaces the inline banner and does NOT refresh: the server
   *  state didn't change, so there is nothing new to pull. Only a confirmed
   *  success clears the banner and re-fetches the authoritative project. */
  const runMutation = async (request: Promise<ApiResult<unknown>>): Promise<boolean> => {
    const result = await request
    if (!result.ok) {
      setSaveError(result.error)
      return false
    }
    setSaveError(null)
    onRefresh()
    return true
  }

  /** Multipart body for the create/edit routes. Sent through `apiRequest`
   *  rather than `apiPost`/`apiPut` because those JSON-encode: FormData must
   *  reach `fetch` untouched so the browser sets its own multipart boundary. */
  const buildCharacterFormData = (
    images: FileList | null,
    durableCreationRequestId?: string,
  ): FormData => {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('description', form.description)
    fd.append('voice_id', form.voice_id)
    if (durableCreationRequestId) {
      fd.append('creation_request_id', durableCreationRequestId)
    }
    if (images) {
      Array.from(images).forEach(f => fd.append('reference_images', f))
    }
    return fd
  }

  const handleAdd = async () => {
    if (!form.name.trim()) return
    setSubmitting(true)
    const durableRequestId = creationRequestId.current ?? newCreationRequestId()
    creationRequestId.current = durableRequestId

    const result = await apiRequest(`${API}/projects/${project.id}/characters`, {
      method: 'POST',
      body: buildCharacterFormData(files, durableRequestId),
    })
    setSubmitting(false)
    // On failure the form stays open with the operator's input intact --
    // clearing it would discard work the server never accepted.
    if (!result.ok) {
      setSaveError(result.error)
      const responsePending = parsePendingCreationEnvelope(result.body)
      if (responsePending.kind === 'ready' && responsePending.pending !== null) {
        setPendingCreationLoad(responsePending)
      } else {
        await refreshPendingCreation()
      }
      return
    }

    setSaveError(null)
    setPendingCreationLoad({ kind: 'ready', pending: null })
    onRefresh()
    setForm({ name: '', description: '', voice_id: '' })
    setFiles(null)
    creationRequestId.current = null
    setAdding(false)
  }

  const handleResumeCreation = async () => {
    if (pendingCreationLoad.kind !== 'ready' || !pendingCreationLoad.pending) return
    const pending = pendingCreationLoad.pending
    setSubmitting(true)
    const body = new FormData()
    body.append('creation_request_id', pending.creation_request_id)
    const result = await apiRequest(
      `${API}/projects/${project.id}/characters`,
      { method: 'POST', body },
    )
    setSubmitting(false)
    if (!result.ok) {
      setSaveError(result.error)
      const responsePending = parsePendingCreationEnvelope(result.body)
      if (responsePending.kind === 'ready' && responsePending.pending !== null) {
        setPendingCreationLoad(responsePending)
      } else {
        await refreshPendingCreation()
      }
      return
    }
    creationRequestId.current = null
    setSaveError(null)
    setPendingCreationLoad({ kind: 'ready', pending: null })
    onRefresh()
  }

  const handleReconcileCreation = async () => {
    if (pendingCreationLoad.kind !== 'ready' || !pendingCreationLoad.pending) return
    const pending = pendingCreationLoad.pending
    if (!globalThis.confirm(
      'Only continue if you verified that no paid provider job can be resumed. This removes the recovery reservation.',
    )) return
    setSubmitting(true)
    const result = await apiRequest(
      `${API}/projects/${project.id}/characters/pending-creation`,
      {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          creation_request_id: pending.creation_request_id,
          confirmation: 'reconciled_no_resumable_paid_work',
        }),
      },
    )
    setSubmitting(false)
    if (!result.ok) {
      setSaveError(result.error)
      await refreshPendingCreation()
      return
    }
    creationRequestId.current = null
    setSaveError(null)
    setPendingCreationLoad({ kind: 'ready', pending: null })
    onRefresh()
  }

  const handleDelete = async (cid: string) => {
    await runMutation(apiDelete(`${API}/projects/${project.id}/characters/${cid}`))
  }

  const [editFiles, setEditFiles] = useState<FileList | null>(null)

  const startEdit = (c: any) => {
    setEditingId(c.id)
    setEditFiles(null)
    setForm({ name: c.name, description: c.description || '', voice_id: c.voice_id || '' })
  }

  const handleSaveEdit = async () => {
    if (!editingId) return
    setSubmitting(true)

    // Use FormData if files are being uploaded, otherwise JSON
    const url = `${API}/projects/${project.id}/characters/${editingId}`
    const ok = await runMutation(
      editFiles && editFiles.length > 0
        ? apiRequest(url, { method: 'PUT', body: buildCharacterFormData(editFiles) })
        : apiPut(url, {
          name: form.name,
          description: form.description,
          voice_id: form.voice_id,
        }),
    )
    setSubmitting(false)
    // On failure the inline editor stays open with the edits intact. Closing
    // it (the pre-fix behavior) discarded the operator's work AND painted a
    // rejection -- a 404, a validation error, or the routine 409
    // `project_busy` during a run -- as a successful save.
    if (!ok) return

    setEditingId(null)
    setEditFiles(null)
  }

  return (
    <div className="p-4">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="flex items-center justify-between w-full mb-3"
      >
        <h2 className="text-sm font-semibold text-mut uppercase tracking-wider">
          Characters ({project.characters.length})
        </h2>
        <span className="text-mut text-xs" aria-hidden>{expanded ? '[-]' : '[+]'}</span>
      </button>

      {/* Outside the `expanded` guard on purpose: collapsing the panel must
          not hide the reason a write was rejected. */}
      {saveError && (
        <div role="alert" className="mb-3 rounded border border-fail/50 bg-fail/10 px-3 py-2 text-xs text-fail">
          Could not save: {saveError}
        </div>
      )}

      {pendingCreationLoad.kind === 'loading' && (
        <div role="status" className="mb-3 rounded border border-line bg-app px-3 py-2 text-xs text-mut">
          Checking for recoverable character work…
        </div>
      )}
      {pendingCreationLoad.kind === 'error' && (
        <div role="alert" className="mb-3 rounded border border-fail/50 bg-fail/10 px-3 py-2 text-xs text-fail">
          <p>Character recovery state could not be verified. New paid work is blocked.</p>
          <button
            type="button"
            onClick={() => { void refreshPendingCreation() }}
            className="mt-2 rounded border border-fail/60 px-2 py-1 font-medium"
          >
            Check recovery state again
          </button>
        </div>
      )}
      {pendingCreationLoad.kind === 'ready' && pendingCreationLoad.pending && (
        <section
          role="alert"
          aria-labelledby="pending-character-creation-title"
          className="mb-3 rounded border border-warn/60 bg-warn/10 px-3 py-3 text-xs text-tx"
        >
          <h3 id="pending-character-creation-title" className="font-semibold text-warn">
            Character creation needs attention
          </h3>
          <p className="mt-1">
            {pendingCreationLoad.pending.name}: {pendingCreationLoad.pending.message}
          </p>
          {pendingCreationLoad.pending.provider_job_id && (
            <p className="mt-1 text-mut">
              Provider job: {pendingCreationLoad.pending.provider_job_id}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {pendingCreationLoad.pending.retryable && (
              <button
                type="button"
                onClick={handleResumeCreation}
                disabled={submitting}
                className="rounded bg-acc px-3 py-1.5 font-medium text-white disabled:opacity-40"
              >
                {submitting ? 'Resuming…' : 'Resume pending character creation'}
              </button>
            )}
            <button
              type="button"
              onClick={handleReconcileCreation}
              disabled={submitting}
              className="rounded border border-line px-3 py-1.5 text-mut hover:text-tx disabled:opacity-40"
            >
              I verified this request is reconciled
            </button>
          </div>
        </section>
      )}

      {expanded && (
        <>
          {/* Character List */}
          <div className="space-y-2 mb-3">
            {project.characters.map(c => (
              <div key={c.id} className="bg-app border border-line rounded-lg p-3 group">
                {editingId === c.id ? (
                  /* Inline edit form */
                  <div className="space-y-2">
                    <label
                      htmlFor={`character-edit-name-${c.id}`}
                      className="text-eyebrow text-mut block"
                    >
                      Character name
                    </label>
                    <input
                      id={`character-edit-name-${c.id}`}
                      type="text" value={form.name}
                      onChange={e => setForm({ ...form, name: e.target.value })}
                      className="w-full bg-panel border border-acc/50 rounded px-3 py-1.5 text-sm text-tx focus:outline-none focus:border-acc"
                    />
                    <label
                      htmlFor={`character-edit-description-${c.id}`}
                      className="text-eyebrow text-mut block"
                    >
                      Character description
                    </label>
                    <textarea
                      id={`character-edit-description-${c.id}`}
                      value={form.description}
                      onChange={e => setForm({ ...form, description: e.target.value })}
                      rows={2}
                      className="w-full bg-panel border border-line rounded px-3 py-1.5 text-sm text-tx focus:outline-none focus:border-acc resize-none"
                    />
                    {/* Existing reference images */}
                    {c.reference_images?.length > 0 && (
                      <div>
                        <p className="text-eyebrow text-mut block mb-1">Current references</p>
                        <div className="flex gap-1.5 flex-wrap">
                          {c.reference_images.map((img: string, i: number) => (
                            <img
                              key={i}
                              src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(img)}`}
                              alt={`Ref ${i + 1}`}
                              className="w-12 h-12 object-cover rounded border border-line"
                            />
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Upload new reference images */}
                    <div>
                      <label
                        htmlFor={`character-edit-references-${c.id}`}
                        className="text-eyebrow text-mut block mb-1"
                      >
                        {c.reference_images?.length > 0 ? 'Add more reference photos' : 'Upload reference photos (face visible)'}
                      </label>
                      <input
                        id={`character-edit-references-${c.id}`}
                        type="file" accept="image/*" multiple
                        onChange={e => setEditFiles(e.target.files)}
                        className="w-full text-eyebrow text-mut file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-panel file:text-tx file:text-eyebrow file:cursor-pointer"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button type="button" onClick={handleSaveEdit} disabled={submitting}
                        className="flex-1 bg-ok/80 hover:bg-ok py-1.5 rounded text-white text-xs font-medium">
                        {submitting ? 'Saving...' : 'Save'}
                      </button>
                      <button type="button" onClick={() => { setEditingId(null); setEditFiles(null) }} className="px-3 py-1.5 text-mut text-xs hover:text-tx">
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  /* Display mode */
                  <div className="flex items-start gap-3">
                    {/* Reference image thumbnail */}
                    {c.canonical_reference ? (
                      <img
                        src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(c.canonical_reference)}`}
                        alt={c.name}
                        className="w-14 h-14 object-cover rounded-lg border border-line shrink-0"
                      />
                    ) : c.reference_images?.length > 0 ? (
                      <img
                        src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(c.reference_images[0])}`}
                        alt={c.name}
                        className="w-14 h-14 object-cover rounded-lg border border-line shrink-0"
                      />
                    ) : (
                      <div className="w-14 h-14 rounded-lg border border-dashed border-line bg-panel flex items-center justify-center shrink-0">
                        <span className="text-mut text-lg">?</span>
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-tx text-sm">{c.name}</div>
                      <div className="text-mut text-xs mt-0.5 line-clamp-2">{c.description}</div>
                      <div className="flex gap-1.5 mt-1.5 flex-wrap">
                        {c.canonical_reference && (
                          <span className="text-eyebrow bg-green-900/30 text-ok px-1.5 py-0.5 rounded">
                            Face locked
                          </span>
                        )}
                        {c.reference_images?.length > 0 && (
                          <span className="text-eyebrow bg-panel px-1.5 py-0.5 rounded text-mut">
                            {c.reference_images.length} ref{c.reference_images.length > 1 ? 's' : ''}
                          </span>
                        )}
                        {c.voice_id && (
                          <span className="text-eyebrow bg-purple-900/30 text-acc px-1.5 py-0.5 rounded">
                            Voice assigned
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1 shrink-0">
                      <button type="button" onClick={() => startEdit(c)} className="text-acc hover:text-acc text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-acc">
                        Edit
                      </button>
                      <button type="button" onClick={() => handleDelete(c.id)} className="text-mut hover:text-fail text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-acc">
                        Remove
                      </button>
                    </div>
                  </div>
                )}

                {/* Historical LoRA status — diagnostic and read-only. */}
                {editingId !== c.id && (() => {
                  const load = loraLoads[
                    loraStatusRequestKey(project.id, c.id)
                  ] ?? LOADING_LORA_STATUS
                  const summary = load.kind === 'ready' ? load.summary : null
                  return (
                    <div
                      className="mt-2 space-y-1 border-t border-line pt-2 text-eyebrow"
                      data-policy="dormant"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono uppercase text-mut">LoRA</span>
                        <span className="rounded border border-line bg-panel px-1.5 py-0.5 text-mut">
                          Inactive
                        </span>
                      </div>
                      <p className="text-eyebrow-sm leading-relaxed text-mut">
                        Training, registration, and production use are unavailable. Historical records are read-only.
                      </p>
                      {load.kind === 'loading' && (
                        <p className="text-eyebrow-sm text-mut" role="status">
                          Historical status: loading…
                        </p>
                      )}
                      {load.kind === 'error' && (
                        <p className="text-eyebrow-sm text-fail" role="alert">
                          Historical status could not be loaded · see diagnostics
                        </p>
                      )}
                      {summary && (
                        <p className="text-eyebrow-sm text-mut">
                          Historical status: {summary.status}
                        </p>
                      )}
                      {summary?.artifactRecorded && (
                        <p className="text-eyebrow-sm text-dim">
                          Historical artifact recorded · not used by production
                        </p>
                      )}
                      {summary?.qualityScore !== null && summary?.qualityScore !== undefined && (
                        <p className="text-eyebrow-sm text-mut">
                          Quality {summary.qualityScore.toFixed(2)} · not used by production
                        </p>
                      )}
                      {summary?.verdict && (
                        <p className="text-eyebrow-sm text-mut">
                          Historical verdict: {summary.verdict}
                        </p>
                      )}
                      {summary?.containsError && (
                        <p className="text-eyebrow-sm text-fail">
                          Historical record contains an error · see diagnostics
                        </p>
                      )}
                    </div>
                  )
                })()}
              </div>
            ))}
          </div>

          {/* Add Character Form */}
          {pendingCreationLoad.kind === 'ready' && pendingCreationLoad.pending === null && (adding ? (
            <div className="bg-app border border-acc/30 rounded-lg p-3 space-y-2">
              <label htmlFor="new-character-name" className="text-xs text-mut block">
                Character name
              </label>
              <input
                id="new-character-name"
                type="text" placeholder="Character name"
                value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full bg-panel border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc"
              />
              <label htmlFor="new-character-description" className="text-xs text-mut block">
                Character description
              </label>
              <textarea
                id="new-character-description"
                placeholder="Physical description (hair, build, clothing, age...)"
                value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                rows={3}
                className="w-full bg-panel border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc resize-none"
              />
              <div>
                <label htmlFor="new-character-references" className="text-xs text-mut block mb-1">Reference photos (face visible)</label>
                <input
                  id="new-character-references"
                  type="file" accept="image/*" multiple
                  onChange={e => setFiles(e.target.files)}
                  className="w-full text-xs text-mut file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-panel file:text-tx file:text-xs file:cursor-pointer"
                />
              </div>
              {config && (
                <div>
                  <label htmlFor="new-character-voice" className="text-xs text-mut block mb-1">Voice</label>
                  <select
                    id="new-character-voice"
                    value={form.voice_id} onChange={e => setForm({ ...form, voice_id: e.target.value })}
                    className="w-full bg-panel border border-line rounded px-3 py-2 text-sm text-tx focus:outline-none"
                  >
                    <option value="">Auto-assign</option>
                    {['woman', 'man', 'child', 'young', 'elderly', 'narrator'].map(cat => {
                      const voices = config.voice_pool.filter((v: any) => v.category === cat)
                      if (voices.length === 0) return null
                      return (
                        <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                          {voices.map((v: any) => (
                            <option key={v.id} value={v.id}>{v.name} — {v.style}</option>
                          ))}
                        </optgroup>
                      )
                    })}
                  </select>
                </div>
              )}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleAdd} disabled={submitting || !form.name.trim()}
                  className="flex-1 bg-acc hover:bg-acc disabled:opacity-40 py-2 rounded text-white text-sm font-medium"
                >
                  {submitting ? 'Creating...' : 'Add Character'}
                </button>
                <button type="button" onClick={() => { creationRequestId.current = null; setAdding(false) }} className="px-4 py-2 text-mut text-sm hover:text-tx">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => { creationRequestId.current = null; setAdding(true) }}
              className="w-full border border-dashed border-line hover:border-acc rounded-lg py-2 text-mut hover:text-acc text-sm transition-colors"
            >
              + Add Character
            </button>
          ))}
        </>
      )}
    </div>
  )
}
