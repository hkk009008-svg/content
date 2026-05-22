import { useState } from 'react'
import type { Project, ProductObject, SurfaceType } from '../types/project'

const API = '/api'

interface Props {
  project: Project
  onRefresh: () => void
}

interface ObjectForm {
  name: string
  brand: string
  description: string
  material_traits: string
  surface_type: SurfaceType
  branding_constraints: string
  scale_reference: string
  texture_anchor: string
}

const EMPTY_FORM: ObjectForm = {
  name: '',
  brand: '',
  description: '',
  material_traits: '',
  surface_type: 'matte',
  branding_constraints: '',
  scale_reference: '',
  texture_anchor: '',
}

const SURFACE_OPTIONS: { value: SurfaceType; label: string; hint: string }[] = [
  { value: 'matte',       label: 'Matte',       hint: 'soft, non-reflective — fabric, paper, ceramic' },
  { value: 'glossy',      label: 'Glossy',      hint: 'high gloss — lacquered, polished plastic' },
  { value: 'metallic',    label: 'Metallic',    hint: 'metal — aluminum, gold, chrome' },
  { value: 'translucent', label: 'Translucent', hint: 'partial light through — glass, frosted, jewel' },
  { value: 'mixed',       label: 'Mixed',       hint: 'multiple surfaces — e.g., metal body + matte cap' },
]

export default function ObjectPanel({ project, onRefresh }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<ObjectForm>(EMPTY_FORM)
  const [files, setFiles] = useState<FileList | null>(null)
  const [editFiles, setEditFiles] = useState<FileList | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const objects: ProductObject[] = (project as any).objects || []

  const handleAdd = async () => {
    if (!form.name.trim()) return
    setSubmitting(true)
    const fd = new FormData()
    Object.entries(form).forEach(([k, v]) => fd.append(k, v))
    if (files) Array.from(files).forEach(f => fd.append('reference_images', f))
    await fetch(`${API}/projects/${project.id}/objects`, { method: 'POST', body: fd })
    setForm(EMPTY_FORM)
    setFiles(null)
    setAdding(false)
    setSubmitting(false)
    onRefresh()
  }

  const handleDelete = async (oid: string) => {
    if (!confirm('Delete this object?')) return
    await fetch(`${API}/projects/${project.id}/objects/${oid}`, { method: 'DELETE' })
    onRefresh()
  }

  const startEdit = (o: ProductObject) => {
    setEditingId(o.id)
    setEditFiles(null)
    setForm({
      name: o.name,
      brand: o.brand || '',
      description: o.description || '',
      material_traits: o.material_traits || '',
      surface_type: o.surface_type || 'matte',
      branding_constraints: o.branding_constraints || '',
      scale_reference: o.scale_reference || '',
      texture_anchor: o.texture_anchor || '',
    })
  }

  const handleSaveEdit = async () => {
    if (!editingId) return
    setSubmitting(true)
    if (editFiles && editFiles.length > 0) {
      const fd = new FormData()
      Object.entries(form).forEach(([k, v]) => fd.append(k, v))
      Array.from(editFiles).forEach(f => fd.append('reference_images', f))
      await fetch(`${API}/projects/${project.id}/objects/${editingId}`, { method: 'PUT', body: fd })
    } else {
      await fetch(`${API}/projects/${project.id}/objects/${editingId}`, {
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

  const cancelEdit = () => {
    setEditingId(null)
    setEditFiles(null)
    setForm(EMPTY_FORM)
  }

  return (
    <div className="p-4">
      <button onClick={() => setExpanded(!expanded)} className="flex items-center justify-between w-full mb-3">
        <h2 className="text-sm font-semibold text-cinema-muted uppercase tracking-wider">
          Objects / Products ({objects.length})
        </h2>
        <span className="text-cinema-muted text-xs">{expanded ? '[-]' : '[+]'}</span>
      </button>

      {expanded && (
        <>
          {objects.length === 0 && !adding && (
            <p className="text-[10px] text-cinema-muted italic mb-3">
              Add product/prop objects for commercials. Each object gets reference-image conditioning
              + identity anchor + brand-locked generation across all shots.
            </p>
          )}

          {/* Object cards */}
          <div className="space-y-2 mb-3">
            {objects.map(o => (
              <div key={o.id} className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2.5">
                {editingId === o.id ? (
                  <ObjectFormFields
                    form={form}
                    setForm={setForm}
                    files={editFiles}
                    setFiles={setEditFiles}
                  />
                ) : (
                  <div className="space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline gap-1.5">
                          <span className="text-xs font-semibold text-cinema-text truncate">{o.name}</span>
                          {o.brand && (
                            <span className="text-[9px] text-cinema-accent font-mono uppercase">{o.brand}</span>
                          )}
                        </div>
                        <p className="text-[10px] text-cinema-muted line-clamp-2">{o.description}</p>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <button onClick={() => startEdit(o)}
                          className="text-[10px] px-1.5 py-0.5 rounded border border-cinema-border-subtle text-cinema-muted hover:text-cinema-text">
                          Edit
                        </button>
                        <button onClick={() => handleDelete(o.id)}
                          className="text-[10px] px-1.5 py-0.5 rounded border border-cinema-danger/30 text-cinema-danger hover:bg-cinema-danger/10">
                          ✕
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-cinema-panel text-cinema-muted font-mono">
                        {o.surface_type}
                      </span>
                      {o.material_traits && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-cinema-panel text-cinema-muted line-clamp-1 max-w-[200px]" title={o.material_traits}>
                          {o.material_traits.slice(0, 32)}{o.material_traits.length > 32 ? '…' : ''}
                        </span>
                      )}
                      {o.reference_images?.length > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-cinema-accent/10 text-cinema-accent font-mono">
                          {o.reference_images.length} ref{o.reference_images.length === 1 ? '' : 's'}
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {editingId === o.id && (
                  <div className="flex gap-2 mt-2 pt-2 border-t border-cinema-border-subtle">
                    <button onClick={handleSaveEdit} disabled={submitting}
                      className="flex-1 text-[10px] px-2 py-1.5 rounded bg-cinema-accent text-white disabled:opacity-50">
                      {submitting ? 'Saving…' : 'Save'}
                    </button>
                    <button onClick={cancelEdit}
                      className="text-[10px] px-2 py-1.5 rounded border border-cinema-border-subtle text-cinema-muted">
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Add new */}
          {adding ? (
            <div className="rounded-lg border border-cinema-accent/30 bg-cinema-bg p-3 space-y-2">
              <ObjectFormFields form={form} setForm={setForm} files={files} setFiles={setFiles} />
              <div className="flex gap-2 pt-2 border-t border-cinema-border-subtle">
                <button onClick={handleAdd} disabled={!form.name.trim() || submitting}
                  className="flex-1 text-[11px] px-3 py-1.5 rounded bg-cinema-accent text-white disabled:opacity-50">
                  {submitting ? 'Adding…' : 'Add Object'}
                </button>
                <button onClick={() => { setAdding(false); setForm(EMPTY_FORM); setFiles(null) }}
                  className="text-[11px] px-3 py-1.5 rounded border border-cinema-border-subtle text-cinema-muted">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button onClick={() => setAdding(true)}
              className="w-full text-[11px] px-3 py-2 rounded-lg border border-dashed border-cinema-border-subtle text-cinema-muted hover:text-cinema-accent hover:border-cinema-accent/40">
              + Add object / product
            </button>
          )}
        </>
      )}
    </div>
  )
}

function ObjectFormFields({
  form, setForm, files, setFiles,
}: {
  form: ObjectForm
  setForm: (f: ObjectForm) => void
  files: FileList | null
  setFiles: (f: FileList | null) => void
}) {
  const update = <K extends keyof ObjectForm>(k: K, v: ObjectForm[K]) => setForm({ ...form, [k]: v })
  return (
    <div className="space-y-2">
      {/* Name + brand */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Name</label>
          <input type="text" value={form.name}
            onChange={e => update('name', e.target.value)}
            placeholder="Aurora Bottle"
            className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[11px] text-cinema-text" />
        </div>
        <div>
          <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Brand</label>
          <input type="text" value={form.brand}
            onChange={e => update('brand', e.target.value)}
            placeholder="Aurora Beverages"
            className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[11px] text-cinema-text" />
        </div>
      </div>

      {/* Description */}
      <div>
        <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Description</label>
        <textarea value={form.description}
          onChange={e => update('description', e.target.value)}
          placeholder="Tall cobalt-blue glass bottle with gold foil label, tapered neck, embossed bottom seal."
          rows={2}
          className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text" />
      </div>

      {/* Surface type — critical for lighting decisions */}
      <div>
        <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Surface Type</label>
        <select value={form.surface_type}
          onChange={e => update('surface_type', e.target.value as SurfaceType)}
          className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text">
          {SURFACE_OPTIONS.map(s => (
            <option key={s.value} value={s.value}>{s.label} — {s.hint}</option>
          ))}
        </select>
        <p className="text-[9px] text-cinema-muted mt-0.5">
          Drives lighting strategy: glossy/metallic → controlled reflections + fill cards; matte → soft directional key.
        </p>
      </div>

      {/* Material traits */}
      <div>
        <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Material Traits</label>
        <input type="text" value={form.material_traits}
          onChange={e => update('material_traits', e.target.value)}
          placeholder="cobalt-blue glass body, gold foil label, copper cap"
          className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text" />
      </div>

      {/* Texture anchor — critical for identity */}
      <div>
        <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Hero Features (identity anchor)</label>
        <input type="text" value={form.texture_anchor}
          onChange={e => update('texture_anchor', e.target.value)}
          placeholder="gold 'Aurora' wordmark, embossed wave pattern, neck logo medallion"
          className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text" />
        <p className="text-[9px] text-cinema-muted mt-0.5">
          The features that MUST be preserved across every shot. Drives the negative_constraints — anything missing here triggers regen.
        </p>
      </div>

      {/* Branding constraints */}
      <div>
        <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Branding Constraints</label>
        <input type="text" value={form.branding_constraints}
          onChange={e => update('branding_constraints', e.target.value)}
          placeholder="logo always visible, centered, legible at any distance; never cropped"
          className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text" />
      </div>

      {/* Scale */}
      <div>
        <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Scale Reference</label>
        <input type="text" value={form.scale_reference}
          onChange={e => update('scale_reference', e.target.value)}
          placeholder="fits in adult hand, ~24cm tall, hand-sized"
          className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text" />
      </div>

      {/* Reference images — multi-angle ideal */}
      <div>
        <label className="text-[10px] text-cinema-text-secondary block mb-0.5 uppercase tracking-wider">Reference Images</label>
        <input type="file" accept="image/*" multiple
          onChange={e => setFiles(e.target.files)}
          className="w-full text-[10px] text-cinema-muted file:bg-cinema-panel file:border-0 file:px-2 file:py-1 file:rounded file:text-cinema-text file:text-[10px]" />
        <p className="text-[9px] text-cinema-muted mt-0.5">
          Best quality with 4-8 images from multiple angles (front, ¾L, ¾R, side, top, detail). IP-Adapter conditions on the canonical reference.
        </p>
      </div>
    </div>
  )
}
