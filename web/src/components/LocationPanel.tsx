import { useState } from 'react'
import type { Project, AppConfig } from '../types/project'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

export default function LocationPanel({ project, config, onRefresh }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', description: '', lighting: '', time_of_day: 'day', weather: 'clear' })
  const [files, setFiles] = useState<FileList | null>(null)
  const [editFiles, setEditFiles] = useState<FileList | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleAdd = async () => {
    if (!form.name.trim()) return
    setSubmitting(true)
    const fd = new FormData()
    Object.entries(form).forEach(([k, v]) => fd.append(k, v))
    if (files) Array.from(files).forEach(f => fd.append('reference_images', f))

    await fetch(`${API}/projects/${project.id}/locations`, { method: 'POST', body: fd })
    setForm({ name: '', description: '', lighting: '', time_of_day: 'day', weather: 'clear' })
    setFiles(null)
    setAdding(false)
    setSubmitting(false)
    onRefresh()
  }

  const handleDelete = async (lid: string) => {
    await fetch(`${API}/projects/${project.id}/locations/${lid}`, { method: 'DELETE' })
    onRefresh()
  }

  const startEdit = (l: any) => {
    setEditingId(l.id)
    setEditFiles(null)
    setForm({ name: l.name, description: l.description || '', lighting: l.lighting || '', time_of_day: l.time_of_day || 'day', weather: l.weather || 'clear' })
  }

  const handleSaveEdit = async () => {
    if (!editingId) return
    setSubmitting(true)
    if (editFiles && editFiles.length > 0) {
      const fd = new FormData()
      Object.entries(form).forEach(([k, v]) => fd.append(k, v))
      Array.from(editFiles).forEach(f => fd.append('reference_images', f))
      await fetch(`${API}/projects/${project.id}/locations/${editingId}`, { method: 'PUT', body: fd })
    } else {
      await fetch(`${API}/projects/${project.id}/locations/${editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
    }
    setEditingId(null)
    setEditFiles(null)
    setSubmitting(false)
    onRefresh()
  }

  const timeOptions = ['dawn', 'morning', 'day', 'afternoon', 'evening', 'night', 'golden_hour']
  const weatherOptions = ['clear', 'rain', 'snow', 'fog', 'overcast', 'storm']

  return (
    <div className="p-4">
      <button onClick={() => setExpanded(!expanded)} className="flex items-center justify-between w-full mb-3">
        <h2 className="text-sm font-semibold text-cinema-muted uppercase tracking-wider">
          Locations ({project.locations.length})
        </h2>
        <span className="text-cinema-muted text-xs">{expanded ? '[-]' : '[+]'}</span>
      </button>

      {expanded && (
        <>
          <div className="space-y-2 mb-3">
            {project.locations.map(l => (
              <div key={l.id} className="bg-cinema-bg border border-cinema-border rounded-lg p-3 group">
                {editingId === l.id ? (
                  <div className="space-y-2">
                    <input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                      className="w-full bg-cinema-panel border border-cinema-accent/50 rounded px-3 py-1.5 text-sm text-cinema-text focus:outline-none focus:border-cinema-accent" />
                    <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} rows={2}
                      className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-1.5 text-sm text-cinema-text focus:outline-none focus:border-cinema-accent resize-none" />
                    <input type="text" value={form.lighting} onChange={e => setForm({ ...form, lighting: e.target.value })}
                      placeholder="Custom lighting (optional)"
                      className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-1.5 text-xs text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent" />
                    <div className="grid grid-cols-2 gap-2">
                      <select value={form.time_of_day} onChange={e => setForm({ ...form, time_of_day: e.target.value })}
                        className="bg-cinema-panel border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text focus:outline-none">
                        {timeOptions.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
                      </select>
                      <select value={form.weather} onChange={e => setForm({ ...form, weather: e.target.value })}
                        className="bg-cinema-panel border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text focus:outline-none">
                        {weatherOptions.map(w => <option key={w} value={w}>{w}</option>)}
                      </select>
                    </div>
                    {/* Existing reference images */}
                    {l.reference_images?.length > 0 && (
                      <div>
                        <label className="text-[10px] text-cinema-muted block mb-1">Current references</label>
                        <div className="flex gap-1.5 flex-wrap">
                          {l.reference_images.map((img: string, i: number) => (
                            <img key={i}
                              src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(img)}`}
                              alt={`Ref ${i + 1}`}
                              className="w-16 h-10 object-cover rounded border border-cinema-border" />
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Upload reference images */}
                    <div>
                      <label className="text-[10px] text-cinema-muted block mb-1">
                        {l.reference_images?.length > 0 ? 'Add more reference photos' : 'Upload reference photos (optional)'}
                      </label>
                      <input type="file" accept="image/*" multiple
                        onChange={e => setEditFiles(e.target.files)}
                        className="w-full text-[10px] text-cinema-muted file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-cinema-panel file:text-cinema-text file:text-[10px] file:cursor-pointer" />
                    </div>
                    <div className="flex gap-2">
                      <button onClick={handleSaveEdit} disabled={submitting}
                        className="flex-1 bg-cinema-success/80 hover:bg-cinema-success py-1.5 rounded text-white text-xs font-medium">
                        {submitting ? 'Saving...' : 'Save'}
                      </button>
                      <button onClick={() => { setEditingId(null); setEditFiles(null) }} className="px-3 py-1.5 text-cinema-muted text-xs hover:text-cinema-text">Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-3">
                    {/* Location thumbnail */}
                    {l.reference_images?.length > 0 ? (
                      <img
                        src={`${API}/projects/${project.id}/file?path=${encodeURIComponent(l.reference_images[0])}`}
                        alt={l.name}
                        className="w-16 h-10 object-cover rounded border border-cinema-border shrink-0"
                      />
                    ) : (
                      <div className="w-16 h-10 rounded border border-dashed border-cinema-border bg-cinema-panel flex items-center justify-center shrink-0">
                        <span className="text-cinema-muted text-[10px]">No ref</span>
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-cinema-text text-sm">{l.name}</div>
                      <div className="text-cinema-muted text-xs mt-0.5 line-clamp-2">{l.description}</div>
                      <div className="flex gap-1.5 mt-1.5 flex-wrap">
                        <span className="text-[10px] bg-cinema-panel px-1.5 py-0.5 rounded text-cinema-muted">{l.time_of_day}</span>
                        {l.weather !== 'clear' && (
                          <span className="text-[10px] bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded">{l.weather}</span>
                        )}
                        {l.reference_images?.length > 0 && (
                          <span className="text-[10px] bg-cinema-panel px-1.5 py-0.5 rounded text-cinema-muted">
                            {l.reference_images.length} ref{l.reference_images.length > 1 ? 's' : ''}
                          </span>
                        )}
                        <span className="text-[10px] bg-cinema-panel px-1.5 py-0.5 rounded text-cinema-muted">seed: {l.seed}</span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 shrink-0">
                      <button onClick={() => startEdit(l)} className="text-cinema-accent hover:text-cinema-accent2 text-xs">Edit</button>
                      <button onClick={() => handleDelete(l.id)} className="text-cinema-muted hover:text-cinema-danger text-xs">Remove</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {adding ? (
            <div className="bg-cinema-bg border border-cinema-accent/30 rounded-lg p-3 space-y-2">
              <input
                type="text" placeholder="Location name"
                value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent"
              />
              <textarea
                placeholder="Describe the environment in detail (architecture, furniture, atmosphere, colors...)"
                value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                rows={3}
                className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent resize-none"
              />
              <input
                type="text" placeholder="Custom lighting (optional, auto-generated from time of day)"
                value={form.lighting} onChange={e => setForm({ ...form, lighting: e.target.value })}
                className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent"
              />
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-cinema-muted block mb-1">Time of Day</label>
                  <select value={form.time_of_day} onChange={e => setForm({ ...form, time_of_day: e.target.value })}
                    className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text focus:outline-none">
                    {timeOptions.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-cinema-muted block mb-1">Weather</label>
                  <select value={form.weather} onChange={e => setForm({ ...form, weather: e.target.value })}
                    className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text focus:outline-none">
                    {weatherOptions.map(w => <option key={w} value={w}>{w}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-cinema-muted block mb-1">Reference photos (optional)</label>
                <input type="file" accept="image/*" multiple onChange={e => setFiles(e.target.files)}
                  className="w-full text-xs text-cinema-muted file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-cinema-panel file:text-cinema-text file:text-xs" />
              </div>
              <div className="flex gap-2">
                <button onClick={handleAdd} disabled={submitting || !form.name.trim()}
                  className="flex-1 bg-cinema-accent hover:bg-cinema-accent2 disabled:opacity-40 py-2 rounded text-white text-sm font-medium">
                  {submitting ? 'Creating...' : 'Add Location'}
                </button>
                <button onClick={() => setAdding(false)} className="px-4 py-2 text-cinema-muted text-sm hover:text-cinema-text">Cancel</button>
              </div>
            </div>
          ) : (
            <button onClick={() => setAdding(true)}
              className="w-full border border-dashed border-cinema-border hover:border-cinema-accent rounded-lg py-2 text-cinema-muted hover:text-cinema-accent text-sm transition-colors">
              + Add Location
            </button>
          )}
        </>
      )}
    </div>
  )
}
