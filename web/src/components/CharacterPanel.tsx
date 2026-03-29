import { useState } from 'react'
import type { Project, AppConfig } from '../types/project'

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
      <button onClick={() => setExpanded(!expanded)} className="flex items-center justify-between w-full mb-3">
        <h2 className="text-sm font-semibold text-cinema-muted uppercase tracking-wider">
          Characters ({project.characters.length})
        </h2>
        <span className="text-cinema-muted text-xs">{expanded ? '[-]' : '[+]'}</span>
      </button>

      {expanded && (
        <>
          {/* Character List */}
          <div className="space-y-2 mb-3">
            {project.characters.map(c => (
              <div key={c.id} className="bg-cinema-bg border border-cinema-border rounded-lg p-3 group">
                {editingId === c.id ? (
                  /* Inline edit form */
                  <div className="space-y-2">
                    <input
                      type="text" value={form.name}
                      onChange={e => setForm({ ...form, name: e.target.value })}
                      className="w-full bg-cinema-panel border border-cinema-accent/50 rounded px-3 py-1.5 text-sm text-cinema-text focus:outline-none focus:border-cinema-accent"
                    />
                    <textarea
                      value={form.description}
                      onChange={e => setForm({ ...form, description: e.target.value })}
                      rows={2}
                      className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-1.5 text-sm text-cinema-text focus:outline-none focus:border-cinema-accent resize-none"
                    />
                    {/* Existing reference images */}
                    {c.reference_images?.length > 0 && (
                      <div>
                        <label className="text-[10px] text-cinema-muted block mb-1">Current references</label>
                        <div className="flex gap-1.5 flex-wrap">
                          {c.reference_images.map((img: string, i: number) => (
                            <img
                              key={i}
                              src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(img)}`}
                              alt={`Ref ${i + 1}`}
                              className="w-12 h-12 object-cover rounded border border-cinema-border"
                            />
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Upload new reference images */}
                    <div>
                      <label className="text-[10px] text-cinema-muted block mb-1">
                        {c.reference_images?.length > 0 ? 'Add more reference photos' : 'Upload reference photos (face visible)'}
                      </label>
                      <input
                        type="file" accept="image/*" multiple
                        onChange={e => setEditFiles(e.target.files)}
                        className="w-full text-[10px] text-cinema-muted file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-cinema-panel file:text-cinema-text file:text-[10px] file:cursor-pointer"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-cinema-muted">PuLID: {form.ip_adapter_weight}</label>
                      <input
                        type="range" min="0.5" max="1.0" step="0.05"
                        value={form.ip_adapter_weight}
                        onChange={e => setForm({ ...form, ip_adapter_weight: e.target.value })}
                        className="w-full accent-cinema-accent"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button onClick={handleSaveEdit} disabled={submitting}
                        className="flex-1 bg-cinema-success/80 hover:bg-cinema-success py-1.5 rounded text-white text-xs font-medium">
                        {submitting ? 'Saving...' : 'Save'}
                      </button>
                      <button onClick={() => { setEditingId(null); setEditFiles(null) }} className="px-3 py-1.5 text-cinema-muted text-xs hover:text-cinema-text">
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
                        className="w-14 h-14 object-cover rounded-lg border border-cinema-border shrink-0"
                      />
                    ) : c.reference_images?.length > 0 ? (
                      <img
                        src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(c.reference_images[0])}`}
                        alt={c.name}
                        className="w-14 h-14 object-cover rounded-lg border border-cinema-border shrink-0"
                      />
                    ) : (
                      <div className="w-14 h-14 rounded-lg border border-dashed border-cinema-border bg-cinema-panel flex items-center justify-center shrink-0">
                        <span className="text-cinema-muted text-lg">?</span>
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-cinema-text text-sm">{c.name}</div>
                      <div className="text-cinema-muted text-xs mt-0.5 line-clamp-2">{c.description}</div>
                      <div className="flex gap-1.5 mt-1.5 flex-wrap">
                        <span className="text-[10px] bg-cinema-panel px-1.5 py-0.5 rounded text-cinema-muted">
                          PuLID: {c.ip_adapter_weight}
                        </span>
                        {c.canonical_reference && (
                          <span className="text-[10px] bg-green-900/30 text-cinema-success px-1.5 py-0.5 rounded">
                            Face locked
                          </span>
                        )}
                        {c.reference_images?.length > 0 && (
                          <span className="text-[10px] bg-cinema-panel px-1.5 py-0.5 rounded text-cinema-muted">
                            {c.reference_images.length} ref{c.reference_images.length > 1 ? 's' : ''}
                          </span>
                        )}
                        {c.voice_id && (
                          <span className="text-[10px] bg-purple-900/30 text-cinema-accent2 px-1.5 py-0.5 rounded">
                            Voice assigned
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 shrink-0">
                      <button onClick={() => startEdit(c)} className="text-cinema-accent hover:text-cinema-accent2 text-xs">
                        Edit
                      </button>
                      <button onClick={() => handleDelete(c.id)} className="text-cinema-muted hover:text-cinema-danger text-xs">
                        Remove
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Add Character Form */}
          {adding ? (
            <div className="bg-cinema-bg border border-cinema-accent/30 rounded-lg p-3 space-y-2">
              <input
                type="text" placeholder="Character name"
                value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent"
              />
              <textarea
                placeholder="Physical description (hair, build, clothing, age...)"
                value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                rows={3}
                className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent resize-none"
              />
              <div>
                <label className="text-xs text-cinema-muted block mb-1">Reference photos (face visible)</label>
                <input
                  type="file" accept="image/*" multiple
                  onChange={e => setFiles(e.target.files)}
                  className="w-full text-xs text-cinema-muted file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-cinema-panel file:text-cinema-text file:text-xs file:cursor-pointer"
                />
              </div>
              {config && (
                <div>
                  <label className="text-xs text-cinema-muted block mb-1">Voice</label>
                  <select
                    value={form.voice_id} onChange={e => setForm({ ...form, voice_id: e.target.value })}
                    className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text focus:outline-none"
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
                <label className="text-xs text-cinema-muted block mb-1">
                  PuLID Face-Lock Strength: {form.ip_adapter_weight}
                </label>
                <input
                  type="range" min="0.5" max="1.0" step="0.05"
                  value={form.ip_adapter_weight}
                  onChange={e => setForm({ ...form, ip_adapter_weight: e.target.value })}
                  className="w-full accent-cinema-accent"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleAdd} disabled={submitting || !form.name.trim()}
                  className="flex-1 bg-cinema-accent hover:bg-cinema-accent2 disabled:opacity-40 py-2 rounded text-white text-sm font-medium"
                >
                  {submitting ? 'Creating...' : 'Add Character'}
                </button>
                <button onClick={() => setAdding(false)} className="px-4 py-2 text-cinema-muted text-sm hover:text-cinema-text">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAdding(true)}
              className="w-full border border-dashed border-cinema-border hover:border-cinema-accent rounded-lg py-2 text-cinema-muted hover:text-cinema-accent text-sm transition-colors"
            >
              + Add Character
            </button>
          )}
        </>
      )}
    </div>
  )
}
