import { useEffect, useState } from 'react'
import type { Project, AppConfig } from '../types/project'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

interface LoraStatus {
  char_id: string
  status: string
  progress_percent: number
  lora_path?: string | null
  quality_score?: number | null
  image_count?: number
  error?: string | null
  finished_at?: string | null
  log_tail?: string | null
}

const MIN_LORA_IMAGES = 15
const IDEAL_LORA_IMAGES = 25

export default function CharacterPanel({ project, config, onRefresh }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', description: '', voice_id: '', ip_adapter_weight: '0.85' })
  const [files, setFiles] = useState<FileList | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [loraStatuses, setLoraStatuses] = useState<Record<string, LoraStatus>>({})
  const [trainingIds, setTrainingIds] = useState<Set<string>>(new Set())

  // Poll LoRA statuses per character — every 5s while any training is active
  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      const updates: Record<string, LoraStatus> = {}
      for (const c of project.characters) {
        try {
          const r = await fetch(`${API}/projects/${project.id}/characters/${c.id}/lora-status`)
          if (r.ok) updates[c.id] = await r.json()
        } catch { /* ignore */ }
      }
      if (!cancelled) setLoraStatuses(prev => ({ ...prev, ...updates }))
    }
    fetchAll()
    const anyActive = Object.values(loraStatuses).some(s => s && (s.status === 'training' || s.status === 'preparing' || s.status === 'validating'))
    if (anyActive || trainingIds.size > 0) {
      const interval = setInterval(fetchAll, 5000)
      return () => { cancelled = true; clearInterval(interval) }
    }
    return () => { cancelled = true }
  }, [project.id, project.characters.length, trainingIds.size])

  const triggerLoraTraining = async (cid: string) => {
    const r = await fetch(`${API}/projects/${project.id}/characters/${cid}/train-lora`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    if (r.ok) {
      setTrainingIds(prev => new Set(prev).add(cid))
      // Optimistically mark status
      setLoraStatuses(prev => ({
        ...prev,
        [cid]: { char_id: cid, status: 'preparing', progress_percent: 0 },
      }))
    } else {
      const err = await r.json().catch(() => ({ error: 'Training failed to start' }))
      alert(`Training failed to start: ${err.error || 'unknown error'}\n${err.have !== undefined ? `Have ${err.have} images, need ${err.needed}` : ''}`)
    }
  }

  const handleAdd = async () => {
    if (!form.name.trim()) return
    setSubmitting(true)

    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('description', form.description)
    fd.append('voice_id', form.voice_id)
    fd.append('ip_adapter_weight', form.ip_adapter_weight)
    if (files) {
      Array.from(files).forEach(f => fd.append('reference_images', f))
    }

    await fetch(`${API}/projects/${project.id}/characters`, { method: 'POST', body: fd })
    setForm({ name: '', description: '', voice_id: '', ip_adapter_weight: '0.85' })
    setFiles(null)
    setAdding(false)
    setSubmitting(false)
    onRefresh()
  }

  const handleDelete = async (cid: string) => {
    await fetch(`${API}/projects/${project.id}/characters/${cid}`, { method: 'DELETE' })
    onRefresh()
  }

  const [editFiles, setEditFiles] = useState<FileList | null>(null)

  const startEdit = (c: any) => {
    setEditingId(c.id)
    setEditFiles(null)
    setForm({ name: c.name, description: c.description || '', voice_id: c.voice_id || '', ip_adapter_weight: String(c.ip_adapter_weight || 0.85) })
  }

  const handleSaveEdit = async () => {
    if (!editingId) return
    setSubmitting(true)

    // Use FormData if files are being uploaded, otherwise JSON
    if (editFiles && editFiles.length > 0) {
      const fd = new FormData()
      fd.append('name', form.name)
      fd.append('description', form.description)
      fd.append('voice_id', form.voice_id)
      fd.append('ip_adapter_weight', form.ip_adapter_weight)
      Array.from(editFiles).forEach(f => fd.append('reference_images', f))
      await fetch(`${API}/projects/${project.id}/characters/${editingId}`, { method: 'PUT', body: fd })
    } else {
      await fetch(`${API}/projects/${project.id}/characters/${editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: form.name, description: form.description, voice_id: form.voice_id, ip_adapter_weight: parseFloat(form.ip_adapter_weight) }),
      })
    }
    setEditingId(null)
    setEditFiles(null)
    setSubmitting(false)
    onRefresh()
  }

  return (
    <div className="p-4">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="flex items-center justify-between w-full mb-3"
      >
        <h2 className="text-sm font-semibold text-editorial-ivory-mute uppercase tracking-wider">
          Characters ({project.characters.length})
        </h2>
        <span className="text-editorial-ivory-mute text-xs" aria-hidden>{expanded ? '[-]' : '[+]'}</span>
      </button>

      {expanded && (
        <>
          {/* Character List */}
          <div className="space-y-2 mb-3">
            {project.characters.map(c => (
              <div key={c.id} className="bg-editorial-ink border border-editorial-rule rounded-lg p-3 group">
                {editingId === c.id ? (
                  /* Inline edit form */
                  <div className="space-y-2">
                    <input
                      type="text" value={form.name}
                      onChange={e => setForm({ ...form, name: e.target.value })}
                      className="w-full bg-editorial-ink-soft border border-editorial-brass/50 rounded px-3 py-1.5 text-sm text-editorial-ivory focus:outline-none focus:border-editorial-brass"
                    />
                    <textarea
                      value={form.description}
                      onChange={e => setForm({ ...form, description: e.target.value })}
                      rows={2}
                      className="w-full bg-editorial-ink-soft border border-editorial-rule rounded px-3 py-1.5 text-sm text-editorial-ivory focus:outline-none focus:border-editorial-brass resize-none"
                    />
                    {/* Existing reference images */}
                    {c.reference_images?.length > 0 && (
                      <div>
                        <label className="text-eyebrow text-editorial-ivory-mute block mb-1">Current references</label>
                        <div className="flex gap-1.5 flex-wrap">
                          {c.reference_images.map((img: string, i: number) => (
                            <img
                              key={i}
                              src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(img)}`}
                              alt={`Ref ${i + 1}`}
                              className="w-12 h-12 object-cover rounded border border-editorial-rule"
                            />
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Upload new reference images */}
                    <div>
                      <label className="text-eyebrow text-editorial-ivory-mute block mb-1">
                        {c.reference_images?.length > 0 ? 'Add more reference photos' : 'Upload reference photos (face visible)'}
                      </label>
                      <input
                        type="file" accept="image/*" multiple
                        onChange={e => setEditFiles(e.target.files)}
                        className="w-full text-eyebrow text-editorial-ivory-mute file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-editorial-ink-soft file:text-editorial-ivory file:text-eyebrow file:cursor-pointer"
                      />
                    </div>
                    <div>
                      <label className="text-eyebrow text-editorial-ivory-mute">PuLID: {form.ip_adapter_weight}</label>
                      <input
                        type="range" min="0.5" max="1.0" step="0.05"
                        value={form.ip_adapter_weight}
                        onChange={e => setForm({ ...form, ip_adapter_weight: e.target.value })}
                        className="w-full accent-editorial-brass"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button onClick={handleSaveEdit} disabled={submitting}
                        className="flex-1 bg-editorial-ready/80 hover:bg-editorial-ready py-1.5 rounded text-white text-xs font-medium">
                        {submitting ? 'Saving...' : 'Save'}
                      </button>
                      <button onClick={() => { setEditingId(null); setEditFiles(null) }} className="px-3 py-1.5 text-editorial-ivory-mute text-xs hover:text-editorial-ivory">
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
                        className="w-14 h-14 object-cover rounded-lg border border-editorial-rule shrink-0"
                      />
                    ) : c.reference_images?.length > 0 ? (
                      <img
                        src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(c.reference_images[0])}`}
                        alt={c.name}
                        className="w-14 h-14 object-cover rounded-lg border border-editorial-rule shrink-0"
                      />
                    ) : (
                      <div className="w-14 h-14 rounded-lg border border-dashed border-editorial-rule bg-editorial-ink-soft flex items-center justify-center shrink-0">
                        <span className="text-editorial-ivory-mute text-lg">?</span>
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-editorial-ivory text-sm">{c.name}</div>
                      <div className="text-editorial-ivory-mute text-xs mt-0.5 line-clamp-2">{c.description}</div>
                      <div className="flex gap-1.5 mt-1.5 flex-wrap">
                        <span className="text-eyebrow bg-editorial-ink-soft px-1.5 py-0.5 rounded text-editorial-ivory-mute">
                          PuLID: {c.ip_adapter_weight}
                        </span>
                        {c.canonical_reference && (
                          <span className="text-eyebrow bg-green-900/30 text-editorial-ready px-1.5 py-0.5 rounded">
                            Face locked
                          </span>
                        )}
                        {c.reference_images?.length > 0 && (
                          <span className="text-eyebrow bg-editorial-ink-soft px-1.5 py-0.5 rounded text-editorial-ivory-mute">
                            {c.reference_images.length} ref{c.reference_images.length > 1 ? 's' : ''}
                          </span>
                        )}
                        {c.voice_id && (
                          <span className="text-eyebrow bg-purple-900/30 text-editorial-brass px-1.5 py-0.5 rounded">
                            Voice assigned
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 shrink-0">
                      <button onClick={() => startEdit(c)} className="text-editorial-brass hover:text-editorial-brass text-xs">
                        Edit
                      </button>
                      <button onClick={() => handleDelete(c.id)} className="text-editorial-ivory-mute hover:text-editorial-curtain text-xs">
                        Remove
                      </button>
                    </div>
                  </div>
                )}

                {/* LoRA training status / trigger — only in display mode */}
                {editingId !== c.id && (() => {
                  const refCount = c.reference_images?.length || 0
                  const status = loraStatuses[c.id]
                  const isActive = status && ['preparing', 'training', 'validating'].includes(status.status)
                  const isDone = status && status.status === 'done' && status.lora_path
                  const isFailed = status && status.status === 'failed'
                  const enoughImages = refCount >= MIN_LORA_IMAGES
                  return (
                    <div className="mt-2 pt-2 border-t border-editorial-rule">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 flex-wrap text-eyebrow">
                          <span className="text-editorial-ivory-mute font-mono uppercase">LoRA:</span>
                          {isDone && (
                            <span className="text-editorial-ready font-bold">✓ trained</span>
                          )}
                          {isActive && (
                            <span className="text-editorial-brass animate-pulse">{status.status}…</span>
                          )}
                          {isFailed && (
                            <span className="text-editorial-curtain" title={status.error || 'unknown'}>✗ failed</span>
                          )}
                          {!status || status.status === 'idle' ? (
                            <span className="text-editorial-ivory-mute">
                              {enoughImages ? 'ready to train' : `${refCount}/${MIN_LORA_IMAGES} images`}
                            </span>
                          ) : null}
                          {isDone && status.quality_score !== null && status.quality_score !== undefined && status.quality_score >= 0 && (
                            <span className="text-editorial-ivory-mute">Q={status.quality_score.toFixed(2)}</span>
                          )}
                        </div>
                        {!isActive && (
                          <button
                            onClick={() => triggerLoraTraining(c.id)}
                            disabled={!enoughImages}
                            title={!enoughImages
                              ? `Need at least ${MIN_LORA_IMAGES} reference images (have ${refCount}). Recommend ${IDEAL_LORA_IMAGES}+ varied angles + lighting.`
                              : isDone ? 'Re-train (overwrites existing LoRA)' : 'Train per-character LoRA (~30 min on RTX 4090)'}
                            className={`text-eyebrow px-2 py-0.5 rounded border ${
                              enoughImages
                                ? 'border-editorial-brass/40 text-editorial-brass hover:bg-editorial-brass/10'
                                : 'border-editorial-rule text-editorial-ivory-mute opacity-50 cursor-not-allowed'
                            }`}>
                            {isDone ? 'Re-train' : isFailed ? 'Retry' : 'Train LoRA'}
                          </button>
                        )}
                      </div>
                      {isFailed && status.error && (
                        <p className="text-eyebrow-sm text-editorial-curtain mt-1 line-clamp-2" title={status.error}>{status.error}</p>
                      )}
                      {isActive && status.image_count !== undefined && status.image_count > 0 && (
                        <p className="text-eyebrow-sm text-editorial-ivory-mute mt-1">
                          Training on {status.image_count} images. ~30 min on RTX 4090.
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
            <div className="bg-editorial-ink border border-editorial-brass/30 rounded-lg p-3 space-y-2">
              <input
                type="text" placeholder="Character name"
                value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full bg-editorial-ink-soft border border-editorial-rule rounded px-3 py-2 text-sm text-editorial-ivory placeholder:text-editorial-ivory-mute focus:outline-none focus:border-editorial-brass"
              />
              <textarea
                placeholder="Physical description (hair, build, clothing, age...)"
                value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                rows={3}
                className="w-full bg-editorial-ink-soft border border-editorial-rule rounded px-3 py-2 text-sm text-editorial-ivory placeholder:text-editorial-ivory-mute focus:outline-none focus:border-editorial-brass resize-none"
              />
              <div>
                <label className="text-xs text-editorial-ivory-mute block mb-1">Reference photos (face visible)</label>
                <input
                  type="file" accept="image/*" multiple
                  onChange={e => setFiles(e.target.files)}
                  className="w-full text-xs text-editorial-ivory-mute file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-editorial-ink-soft file:text-editorial-ivory file:text-xs file:cursor-pointer"
                />
              </div>
              {config && (
                <div>
                  <label className="text-xs text-editorial-ivory-mute block mb-1">Voice</label>
                  <select
                    value={form.voice_id} onChange={e => setForm({ ...form, voice_id: e.target.value })}
                    className="w-full bg-editorial-ink-soft border border-editorial-rule rounded px-3 py-2 text-sm text-editorial-ivory focus:outline-none"
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
              <div>
                <label className="text-xs text-editorial-ivory-mute block mb-1">
                  PuLID Face-Lock Strength: {form.ip_adapter_weight}
                </label>
                <input
                  type="range" min="0.5" max="1.0" step="0.05"
                  value={form.ip_adapter_weight}
                  onChange={e => setForm({ ...form, ip_adapter_weight: e.target.value })}
                  className="w-full accent-editorial-brass"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleAdd} disabled={submitting || !form.name.trim()}
                  className="flex-1 bg-editorial-brass hover:bg-editorial-brass disabled:opacity-40 py-2 rounded text-white text-sm font-medium"
                >
                  {submitting ? 'Creating...' : 'Add Character'}
                </button>
                <button onClick={() => setAdding(false)} className="px-4 py-2 text-editorial-ivory-mute text-sm hover:text-editorial-ivory">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAdding(true)}
              className="w-full border border-dashed border-editorial-rule hover:border-editorial-brass rounded-lg py-2 text-editorial-ivory-mute hover:text-editorial-brass text-sm transition-colors"
            >
              + Add Character
            </button>
          )}
        </>
      )}
    </div>
  )
}
