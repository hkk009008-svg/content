import { useEffect, useRef, useState } from 'react'
import type { Project, AppConfig, LoraStatus } from '../types/project'
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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
  const characterStatusKey = JSON.stringify(project.characters.map((c) => c.id))

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
  const buildCharacterFormData = (images: FileList | null): FormData => {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('description', form.description)
    fd.append('voice_id', form.voice_id)
    if (images) {
      Array.from(images).forEach(f => fd.append('reference_images', f))
    }
    return fd
  }

  const handleAdd = async () => {
    if (!form.name.trim()) return
    setSubmitting(true)

    const ok = await runMutation(apiRequest(`${API}/projects/${project.id}/characters`, {
      method: 'POST',
      body: buildCharacterFormData(files),
    }))
    setSubmitting(false)
    // On failure the form stays open with the operator's input intact --
    // clearing it would discard work the server never accepted.
    if (!ok) return

    setForm({ name: '', description: '', voice_id: '' })
    setFiles(null)
    setAdding(false)
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

      {expanded && (
        <>
          {/* Character List */}
          <div className="space-y-2 mb-3">
            {project.characters.map(c => (
              <div key={c.id} className="bg-app border border-line rounded-lg p-3 group">
                {editingId === c.id ? (
                  /* Inline edit form */
                  <div className="space-y-2">
                    <input
                      type="text" value={form.name}
                      onChange={e => setForm({ ...form, name: e.target.value })}
                      className="w-full bg-panel border border-acc/50 rounded px-3 py-1.5 text-sm text-tx focus:outline-none focus:border-acc"
                    />
                    <textarea
                      value={form.description}
                      onChange={e => setForm({ ...form, description: e.target.value })}
                      rows={2}
                      className="w-full bg-panel border border-line rounded px-3 py-1.5 text-sm text-tx focus:outline-none focus:border-acc resize-none"
                    />
                    {/* Existing reference images */}
                    {c.reference_images?.length > 0 && (
                      <div>
                        <label className="text-eyebrow text-mut block mb-1">Current references</label>
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
                      <label className="text-eyebrow text-mut block mb-1">
                        {c.reference_images?.length > 0 ? 'Add more reference photos' : 'Upload reference photos (face visible)'}
                      </label>
                      <input
                        type="file" accept="image/*" multiple
                        onChange={e => setEditFiles(e.target.files)}
                        className="w-full text-eyebrow text-mut file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-panel file:text-tx file:text-eyebrow file:cursor-pointer"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button onClick={handleSaveEdit} disabled={submitting}
                        className="flex-1 bg-ok/80 hover:bg-ok py-1.5 rounded text-white text-xs font-medium">
                        {submitting ? 'Saving...' : 'Save'}
                      </button>
                      <button onClick={() => { setEditingId(null); setEditFiles(null) }} className="px-3 py-1.5 text-mut text-xs hover:text-tx">
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
                    <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 shrink-0">
                      <button onClick={() => startEdit(c)} className="text-acc hover:text-acc text-xs">
                        Edit
                      </button>
                      <button onClick={() => handleDelete(c.id)} className="text-mut hover:text-fail text-xs">
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
          {adding ? (
            <div className="bg-app border border-acc/30 rounded-lg p-3 space-y-2">
              <input
                type="text" placeholder="Character name"
                value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full bg-panel border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc"
              />
              <textarea
                placeholder="Physical description (hair, build, clothing, age...)"
                value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                rows={3}
                className="w-full bg-panel border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc resize-none"
              />
              <div>
                <label className="text-xs text-mut block mb-1">Reference photos (face visible)</label>
                <input
                  type="file" accept="image/*" multiple
                  onChange={e => setFiles(e.target.files)}
                  className="w-full text-xs text-mut file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-panel file:text-tx file:text-xs file:cursor-pointer"
                />
              </div>
              {config && (
                <div>
                  <label className="text-xs text-mut block mb-1">Voice</label>
                  <select
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
                  onClick={handleAdd} disabled={submitting || !form.name.trim()}
                  className="flex-1 bg-acc hover:bg-acc disabled:opacity-40 py-2 rounded text-white text-sm font-medium"
                >
                  {submitting ? 'Creating...' : 'Add Character'}
                </button>
                <button onClick={() => setAdding(false)} className="px-4 py-2 text-mut text-sm hover:text-tx">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAdding(true)}
              className="w-full border border-dashed border-line hover:border-acc rounded-lg py-2 text-mut hover:text-acc text-sm transition-colors"
            >
              + Add Character
            </button>
          )}
        </>
      )}
    </div>
  )
}
