import { useEffect, useState } from 'react'
import type { Project, AppConfig, LoraStatus } from '../types/project'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

export default function CharacterPanel({ project, config, onRefresh }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', description: '', voice_id: '', ip_adapter_weight: '0.85' })
  const [files, setFiles] = useState<FileList | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [loraStatuses, setLoraStatuses] = useState<Record<string, LoraStatus>>({})
  const characterStatusKey = JSON.stringify(project.characters.map((c) => c.id))

  // One diagnostic GET per character. Even a legacy "training" state is
  // historical: dormant-policy fields can never restore an action or polling.
  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      const entries = await Promise.all(project.characters.map(async (c) => {
        try {
          const r = await fetch(`${API}/projects/${project.id}/characters/${c.id}/lora-status`)
          if (r.ok) return [c.id, await r.json() as LoraStatus] as const
        } catch { /* ignore */ }
        return null
      }))
      if (!cancelled) {
        setLoraStatuses(Object.fromEntries(entries.filter((entry) => entry !== null)))
      }
    }
    void fetchAll()
    return () => { cancelled = true }
  }, [project.id, characterStatusKey]) // eslint-disable-line react-hooks/exhaustive-deps

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
        <h2 className="text-sm font-semibold text-mut uppercase tracking-wider">
          Characters ({project.characters.length})
        </h2>
        <span className="text-mut text-xs" aria-hidden>{expanded ? '[-]' : '[+]'}</span>
      </button>

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
                    <div>
                      <label className="text-eyebrow text-mut">PuLID: {form.ip_adapter_weight}</label>
                      <input
                        type="range" min="0.5" max="1.0" step="0.05"
                        value={form.ip_adapter_weight}
                        onChange={e => setForm({ ...form, ip_adapter_weight: e.target.value })}
                        className="w-full accent-acc"
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
                        <span className="text-eyebrow bg-panel px-1.5 py-0.5 rounded text-mut">
                          PuLID: {c.ip_adapter_weight}
                        </span>
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
                  const status = loraStatuses[c.id]
                  const historicalVerdict = status?.rejected
                    ? 'rejected'
                    : status?.quality_warning
                      ? 'warning'
                      : status?.quality_score !== null && status?.quality_score !== undefined
                        ? 'recorded'
                        : null
                  return (
                    <div
                      className="mt-2 space-y-1 border-t border-line pt-2 text-eyebrow"
                      data-policy={status?.policy ?? 'dormant'}
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
                      <p className="text-eyebrow-sm text-mut">
                        Historical status: {status?.status ?? 'unavailable'}
                      </p>
                      {status?.lora_path && (
                        <p className="break-all text-eyebrow-sm text-dim">
                          Historical path: {status.lora_path}
                        </p>
                      )}
                      {status?.quality_score !== null && status?.quality_score !== undefined && (
                        <p className="text-eyebrow-sm text-mut">
                          Quality {status.quality_score.toFixed(2)} · not used by production
                        </p>
                      )}
                      {historicalVerdict && (
                        <p className="text-eyebrow-sm text-mut">
                          Historical verdict: {historicalVerdict}
                        </p>
                      )}
                      {status?.error && (
                        <p className="line-clamp-2 text-eyebrow-sm text-fail" title={status.error}>
                          Historical error: {status.error}
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
              <div>
                <label className="text-xs text-mut block mb-1">
                  PuLID Face-Lock Strength: {form.ip_adapter_weight}
                </label>
                <input
                  type="range" min="0.5" max="1.0" step="0.05"
                  value={form.ip_adapter_weight}
                  onChange={e => setForm({ ...form, ip_adapter_weight: e.target.value })}
                  className="w-full accent-acc"
                />
              </div>
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
