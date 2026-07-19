import { useState } from 'react'
import type { Project, AppConfig, Scene } from '../types/project'
import { classifyShotType, getSceneGuidance, getShotTemplate } from '../lib/guidance'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

export default function ScenePanel({ project, config, onRefresh }: Props) {
  const [editing, setEditing] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [draggedId, setDraggedId] = useState<string | null>(null)
  const [dragOverId, setDragOverId] = useState<string | null>(null)
  const [form, setForm] = useState({
    title: '', location_id: '', characters_present: [] as string[],
    action: '', dialogue: '', mood: 'cinematic', camera_direction: '', duration_seconds: '5',
  })
  const [generatingDialogue, setGeneratingDialogue] = useState<string | null>(null)

  const handleAdd = async () => {
    if (!form.title.trim()) return
    await fetch(`${API}/projects/${project.id}/scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, duration_seconds: parseFloat(form.duration_seconds) }),
    })
    setForm({ title: '', location_id: '', characters_present: [], action: '', dialogue: '', mood: 'cinematic', camera_direction: '', duration_seconds: '5' })
    setAdding(false)
    onRefresh()
  }

  const handleUpdate = async (sid: string, updates: Partial<Scene>) => {
    await fetch(`${API}/projects/${project.id}/scenes/${sid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    })
    onRefresh()
  }

  const handleDelete = async (sid: string) => {
    await fetch(`${API}/projects/${project.id}/scenes/${sid}`, { method: 'DELETE' })
    onRefresh()
  }

  const handleGenerateDialogue = async (sid: string) => {
    // Check if characters are assigned
    const scene = project.scenes.find(s => s.id === sid)
    if (!scene?.characters_present?.length) {
      alert('Assign at least one character to this scene first')
      return
    }
    if (!scene?.action?.trim()) {
      alert('Add an action description first so dialogue can be generated from it')
      return
    }

    setGeneratingDialogue(sid)
    try {
      const res = await fetch(`${API}/projects/${project.id}/scenes/${sid}/generate-dialogue`, { method: 'POST' })
      const data = await res.json()
      if (res.ok && data.dialogue_lines?.length) {
        const dialogueText = data.dialogue_lines.map((l: any) => `${l.character_name}: ${l.text}`).join('\n')
        await handleUpdate(sid, { dialogue: dialogueText })
      } else if (data.dialogue_lines?.length === 0) {
        alert('No dialogue generated — try adding more detail to the action description')
      } else {
        alert(`Dialogue generation failed: ${data.error || 'Unknown error'}`)
      }
    } catch (e) {
      alert(`Network error: ${e}`)
    }
    setGeneratingDialogue(null)
  }

  const handleDecompose = async (sid: string) => {
    await fetch(`${API}/projects/${project.id}/scenes/${sid}/decompose`, { method: 'POST' })
    onRefresh()
  }

  const handleDragStart = (sceneId: string) => {
    setDraggedId(sceneId)
  }

  const handleDragOver = (e: React.DragEvent, sceneId: string) => {
    e.preventDefault()
    setDragOverId(sceneId)
  }

  const handleDrop = async (targetId: string) => {
    if (!draggedId || draggedId === targetId) {
      setDraggedId(null)
      setDragOverId(null)
      return
    }
    // Compute new order
    const ids = project.scenes.map(s => s.id)
    const fromIdx = ids.indexOf(draggedId)
    const toIdx = ids.indexOf(targetId)
    if (fromIdx === -1 || toIdx === -1) return

    ids.splice(fromIdx, 1)
    ids.splice(toIdx, 0, draggedId)

    setDraggedId(null)
    setDragOverId(null)

    await fetch(`${API}/projects/${project.id}/scenes/reorder`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene_ids: ids }),
    })
    onRefresh()
  }

  const toggleCharacter = (charId: string) => {
    setForm(f => ({
      ...f,
      characters_present: f.characters_present.includes(charId)
        ? f.characters_present.filter(c => c !== charId)
        : [...f.characters_present, charId],
    }))
  }

  const addSceneGuidance = getSceneGuidance({
    id: 'draft',
    order: 0,
    title: form.title,
    location_id: form.location_id,
    characters_present: form.characters_present,
    action: form.action,
    dialogue: form.dialogue,
    mood: form.mood,
    camera_direction: form.camera_direction,
    duration_seconds: parseFloat(form.duration_seconds || '0') || 0,
    num_shots: 0,
    shots: [],
  })

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-mut uppercase tracking-wider">
          Scene Timeline ({project.scenes.length} scenes)
        </h2>
        <button onClick={() => setAdding(true)}
          className="bg-acc hover:bg-acc px-3 py-1.5 rounded text-white text-xs font-medium">
          + Add Scene
        </button>
      </div>

      {/* Scene List */}
      <div className="space-y-3">
        {project.scenes.map((scene, idx) => (
          <div
            key={scene.id}
            draggable
            onDragStart={() => handleDragStart(scene.id)}
            onDragOver={(e) => handleDragOver(e, scene.id)}
            onDrop={() => handleDrop(scene.id)}
            onDragEnd={() => { setDraggedId(null); setDragOverId(null) }}
            className={`bg-panel border rounded-lg overflow-hidden transition-all ${
              dragOverId === scene.id ? 'border-acc ring-1 ring-acc/50' :
              draggedId === scene.id ? 'opacity-50 border-line' : 'border-line'
            }`}
          >
            {/* Scene Header */}
            <div
              className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-app/50"
              onClick={() => setEditing(editing === scene.id ? null : scene.id)}
            >
              <div className="flex items-center gap-3">
                <span className="text-mut text-xs font-mono w-6">{idx + 1}</span>
                <div>
                  <div className="text-tx text-sm font-medium">{scene.title}</div>
                  <div className="text-mut text-xs mt-0.5">
                    {scene.characters_present.length} chars
                    {scene.location_id && ` / ${project.locations.find(l => l.id === scene.location_id)?.name || 'Unknown'}`}
                    {' / '}{scene.duration_seconds}s
                    {scene.num_shots > 0 && ` / ${scene.num_shots} shots`}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-eyebrow px-2 py-0.5 rounded ${scene.mood === 'tense' ? 'bg-red-900/30 text-red-400' : scene.mood === 'melancholic' ? 'bg-blue-900/30 text-blue-400' : 'bg-app text-mut'}`}>
                  {scene.mood}
                </span>
                <button onClick={e => { e.stopPropagation(); handleDelete(scene.id) }}
                  className="text-mut hover:text-fail text-xs">X</button>
              </div>
            </div>

            {/* Expanded Editor */}
            {editing === scene.id && (
              <div className="border-t border-line px-4 py-3 space-y-3 bg-app/30">
                <div className="text-xs text-mut line-clamp-2">{scene.action}</div>

                {/* Action */}
                <div>
                  <label className="text-xs text-mut block mb-1">Action / What happens</label>
                  <textarea
                    defaultValue={scene.action}
                    onBlur={e => handleUpdate(scene.id, { action: e.target.value })}
                    rows={2} placeholder="Describe what happens in this scene..."
                    className="w-full bg-panel border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc resize-none"
                  />
                </div>

                {/* Dialogue */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs text-mut">Dialogue</label>
                    <button onClick={() => handleGenerateDialogue(scene.id)}
                      disabled={generatingDialogue === scene.id}
                      className="text-eyebrow text-acc hover:text-acc">
                      {generatingDialogue === scene.id ? 'Generating...' : 'Auto-generate'}
                    </button>
                  </div>
                  <textarea
                    defaultValue={scene.dialogue}
                    onBlur={e => handleUpdate(scene.id, { dialogue: e.target.value })}
                    rows={3} placeholder="Character Name: dialogue line..."
                    className="w-full bg-panel border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc resize-none font-mono text-xs"
                  />
                </div>

                {/* Characters in scene */}
                <div>
                  <label className="text-xs text-mut block mb-1">Characters in scene</label>
                  <div className="flex flex-wrap gap-1">
                    {project.characters.map(c => {
                      const active = scene.characters_present.includes(c.id)
                      return (
                        <button key={c.id}
                          onClick={() => handleUpdate(scene.id, {
                            characters_present: active
                              ? scene.characters_present.filter(x => x !== c.id)
                              : [...scene.characters_present, c.id]
                          })}
                          className={`px-2 py-1 rounded text-xs ${active ? 'bg-acc text-white' : 'bg-panel text-mut border border-line'}`}>
                          {c.name}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Location + Mood + Duration row */}
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-xs text-mut block mb-1">Location</label>
                    <select
                      value={scene.location_id}
                      onChange={e => handleUpdate(scene.id, { location_id: e.target.value })}
                      className="w-full bg-panel border border-line rounded px-2 py-1.5 text-xs text-tx">
                      <option value="">None</option>
                      {project.locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-mut block mb-1">Mood</label>
                    <select
                      value={scene.mood}
                      onChange={e => handleUpdate(scene.id, { mood: e.target.value })}
                      className="w-full bg-panel border border-line rounded px-2 py-1.5 text-xs text-tx">
                      {(config?.mood_options || ['cinematic', 'melancholic', 'tense', 'hopeful', 'dark']).map(m =>
                        <option key={m} value={m}>{m}</option>
                      )}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-mut block mb-1">Duration (s)</label>
                    <input type="number" min={2} max={30} step={0.5}
                      value={scene.duration_seconds}
                      onChange={e => handleUpdate(scene.id, { duration_seconds: parseFloat(e.target.value) })}
                      className="w-full bg-panel border border-line rounded px-2 py-1.5 text-xs text-tx" />
                  </div>
                </div>

                {/* Camera direction */}
                <div>
                  <label className="text-xs text-mut block mb-1">Camera direction (optional — AI will decide if blank)</label>
                  <input type="text"
                    defaultValue={scene.camera_direction}
                    onBlur={e => handleUpdate(scene.id, { camera_direction: e.target.value })}
                    placeholder="e.g., Start ECU on hands, pull back to wide, dolly right to reveal..."
                    className="w-full bg-panel border border-line rounded px-3 py-2 text-xs text-tx placeholder:text-mut focus:outline-none focus:border-acc" />
                </div>

                {(() => {
                  const guidance = getSceneGuidance(scene)
                  return (
                    <div className="rounded-lg border border-acc/20 bg-acc/5 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold text-tx">{guidance.title}</div>
                          <p className="mt-1 text-eyebrow-lg leading-relaxed text-mut">{guidance.recommendation}</p>
                        </div>
                        <span className="rounded bg-app px-2 py-0.5 text-eyebrow uppercase tracking-wide text-acc">{guidance.mode}</span>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div>
                          <div className="text-eyebrow font-mono uppercase text-acc">Coverage</div>
                          <div className="mt-1 space-y-1">
                            {guidance.coverage.map((item) => (
                              <div key={item} className="text-eyebrow-lg text-mut">{item}</div>
                            ))}
                          </div>
                        </div>
                        <div>
                          <div className="text-eyebrow font-mono uppercase text-acc">Parameter Focus</div>
                          <div className="mt-1 space-y-1">
                            {guidance.parameterTips.map((item) => (
                              <div key={item} className="text-eyebrow-lg text-mut">{item}</div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })()}

                {/* Shot breakdown preview */}
                {scene.shots && scene.shots.length > 0 && (
                  <div>
                    <label className="text-xs text-mut block mb-1">Shot Breakdown ({scene.shots.length} shots)</label>
                    <div className="space-y-1">
                      {scene.shots.map((shot, si) => {
                        const shotType = classifyShotType(shot)
                        const template = getShotTemplate(shot, config)
                        const recommendedApi = template?.target_api || shot.target_api
                        const objsInFrame = (shot as any).objects_in_frame || []
                        // Live edit handler for target_api override
                        const updateShotApi = async (newApi: string) => {
                          const updatedShots = scene.shots.map(s =>
                            s.id === shot.id ? { ...s, target_api: newApi } : s
                          )
                          await fetch(`${API}/projects/${project.id}/scenes/${scene.id}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ shots: updatedShots }),
                          })
                          onRefresh()
                        }
                        // Live edit handler for objects_in_frame
                        const toggleObjectInFrame = async (oid: string) => {
                          const next = objsInFrame.includes(oid)
                            ? objsInFrame.filter((x: string) => x !== oid)
                            : [...objsInFrame, oid]
                          const updatedShots = scene.shots.map(s =>
                            s.id === shot.id ? { ...s, objects_in_frame: next } : s
                          )
                          await fetch(`${API}/projects/${project.id}/scenes/${scene.id}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ shots: updatedShots }),
                          })
                          onRefresh()
                        }
                        // Filter APIs by modality=video + status live/beta (for the picker)
                        const videoApiOptions = config?.api_registry
                          ? Object.entries(config.api_registry).filter(
                              ([, v]: any) => (v.modality === 'video' || v.category === 'smart') && (v.status || 'live') !== 'planned'
                            )
                          : []
                        return (
                          <div key={shot.id || si} className="rounded bg-panel px-2 py-1.5 text-eyebrow text-mut">
                            <div className="flex gap-2">
                              <span className="font-mono text-acc">{si + 1}</span>
                              <span className="flex-1 line-clamp-1">{shot.prompt?.slice(0, 80)}...</span>
                              <span>{shot.camera}</span>
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-2">
                              <span className="rounded bg-app px-1.5 py-0.5 text-eyebrow-sm uppercase text-acc">{shotType}</span>
                              {template && (
                                <span className="rounded bg-app px-1.5 py-0.5 text-eyebrow-sm">CFG {template.guidance} / {template.steps} steps</span>
                              )}
                              {/* Per-shot API override picker */}
                              <select
                                value={shot.target_api || 'AUTO'}
                                onChange={e => updateShotApi(e.target.value)}
                                className="rounded bg-app border border-line px-1 py-0.5 text-eyebrow-sm text-tx"
                                title="Override target API for this shot">
                                {videoApiOptions.map(([k, v]: any) => (
                                  <option key={k} value={k}>
                                    {v.label}{v.per_shot_cost ? ` ($${v.per_shot_cost.toFixed(2)})` : ''}
                                  </option>
                                ))}
                              </select>
                              {shot.target_api && shot.target_api !== recommendedApi && (
                                <span className="text-eyebrow-sm text-warn" title={`Best for ${shotType}: ${recommendedApi}`}>
                                  ⚠ override
                                </span>
                              )}
                            </div>
                            {/* Performance capture status + driving video upload */}
                            <div className="mt-1 flex flex-wrap items-center gap-1">
                              <span className="text-eyebrow-sm text-mut">Performance:</span>
                              {(() => {
                                const eng = (shot as any).performance_engine || ''
                                const approvedId = (shot as any).approved_performance_take_id || ''
                                const drivingUploaded = !!((shot as any).driving_video_path)
                                if (eng === 'SKIP') {
                                  return <span className="text-eyebrow-sm text-mut italic">skipped (wide/no-dialogue)</span>
                                }
                                if (approvedId) {
                                  return (
                                    <>
                                      <span className="text-eyebrow-sm text-ok font-bold">✓ {eng || 'captured'}</span>
                                      <button
                                        onClick={async () => {
                                          if (!confirm('Clear performance take? Next run will regenerate.')) return
                                          await fetch(`${API}/projects/${project.id}/shots/${shot.id}/performance`, { method: 'DELETE' })
                                          onRefresh()
                                        }}
                                        className="text-eyebrow-sm text-fail hover:underline">
                                        clear
                                      </button>
                                    </>
                                  )
                                }
                                return <span className="text-eyebrow-sm text-mut">{eng || 'pending'}</span>
                              })()}
                              {/* Driving video upload (Mode A) */}
                              <label className="text-eyebrow-sm text-acc hover:text-acc cursor-pointer underline ml-2">
                                {((shot as any).driving_video_path) ? '↻ replace driving' : '+ upload driving'}
                                <input
                                  type="file"
                                  accept="video/*"
                                  className="hidden"
                                  onChange={async e => {
                                    const f = e.target.files?.[0]
                                    if (!f) return
                                    const fd = new FormData()
                                    fd.append('driving_video', f)
                                    const r = await fetch(`${API}/projects/${project.id}/shots/${shot.id}/upload-driving-video`, {
                                      method: 'POST', body: fd,
                                    })
                                    if (r.ok) onRefresh()
                                    else alert('Upload failed')
                                  }}
                                />
                              </label>
                            </div>

                            {/* Objects-in-frame editor */}
                            {(project.objects || []).length > 0 && (
                              <div className="mt-1 flex flex-wrap items-center gap-1">
                                <span className="text-eyebrow-sm text-mut">Objects:</span>
                                {(project.objects || []).map((o: any) => {
                                  const inFrame = objsInFrame.includes(o.id)
                                  return (
                                    <button
                                      key={o.id}
                                      onClick={() => toggleObjectInFrame(o.id)}
                                      className={`text-eyebrow-sm px-1.5 py-0.5 rounded border transition-colors ${
                                        inFrame
                                          ? 'bg-acc/20 border-acc/50 text-acc'
                                          : 'bg-app border-line text-mut hover:border-acc/30'
                                      }`}
                                      title={o.brand ? `${o.brand} — ${o.description}` : o.description}>
                                      {inFrame ? '✓ ' : ''}{o.name}
                                    </button>
                                  )
                                })}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                <button onClick={() => handleDecompose(scene.id)}
                  className="w-full border border-acc/40 hover:bg-acc/10 rounded py-1.5 text-acc text-xs">
                  {scene.shots?.length ? 'Re-decompose into shots' : 'Decompose into shots'}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Add Scene Form */}
      {adding && (
        <div className="mt-4 bg-panel border border-acc/30 rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-medium text-tx">New Scene</h3>
          <input type="text" placeholder="Scene title" value={form.title}
            onChange={e => setForm({ ...form, title: e.target.value })}
            className="w-full bg-app border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc" />
          <textarea placeholder="What happens in this scene..."
            value={form.action} onChange={e => setForm({ ...form, action: e.target.value })}
            rows={2} className="w-full bg-app border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc resize-none" />
          <textarea placeholder="Dialogue (optional — can auto-generate later)"
            value={form.dialogue} onChange={e => setForm({ ...form, dialogue: e.target.value })}
            rows={2} className="w-full bg-app border border-line rounded px-3 py-2 text-sm text-tx placeholder:text-mut focus:outline-none focus:border-acc resize-none font-mono text-xs" />
          <div>
            <label className="text-xs text-mut block mb-1">Characters</label>
            <div className="flex flex-wrap gap-1">
              {project.characters.map(c => (
                <button key={c.id} onClick={() => toggleCharacter(c.id)}
                  className={`px-2 py-1 rounded text-xs ${form.characters_present.includes(c.id) ? 'bg-acc text-white' : 'bg-app text-mut border border-line'}`}>
                  {c.name}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <select value={form.location_id} onChange={e => setForm({ ...form, location_id: e.target.value })}
              className="bg-app border border-line rounded px-2 py-1.5 text-xs text-tx">
              <option value="">Location...</option>
              {project.locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
            <select value={form.mood} onChange={e => setForm({ ...form, mood: e.target.value })}
              className="bg-app border border-line rounded px-2 py-1.5 text-xs text-tx">
              {(config?.mood_options || ['cinematic']).map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <input type="number" min={2} max={30} step={0.5} value={form.duration_seconds}
              onChange={e => setForm({ ...form, duration_seconds: e.target.value })}
              className="bg-app border border-line rounded px-2 py-1.5 text-xs text-tx" placeholder="Duration (s)" />
          </div>
          <div className="rounded-lg border border-acc/20 bg-acc/5 p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold text-tx">{addSceneGuidance.title}</div>
                <p className="mt-1 text-eyebrow-lg leading-relaxed text-mut">{addSceneGuidance.recommendation}</p>
              </div>
              <span className="rounded bg-app px-2 py-0.5 text-eyebrow uppercase tracking-wide text-acc">{addSceneGuidance.mode}</span>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <div className="text-eyebrow font-mono uppercase text-acc">Coverage</div>
                <div className="mt-1 space-y-1">
                  {addSceneGuidance.coverage.map((item) => (
                    <div key={item} className="text-eyebrow-lg text-mut">{item}</div>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-eyebrow font-mono uppercase text-acc">Parameter Focus</div>
                <div className="mt-1 space-y-1">
                  {addSceneGuidance.parameterTips.map((item) => (
                    <div key={item} className="text-eyebrow-lg text-mut">{item}</div>
                  ))}
                </div>
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdd} disabled={!form.title.trim()}
              className="flex-1 bg-acc hover:bg-acc disabled:opacity-40 py-2 rounded text-white text-sm font-medium">
              Add Scene
            </button>
            <button onClick={() => setAdding(false)} className="px-4 py-2 text-mut text-sm">Cancel</button>
          </div>
        </div>
      )}

      {project.scenes.length === 0 && !adding && (
        <div className="text-center py-12 text-mut">
          <div className="text-2xl mb-2">No scenes yet</div>
          <p className="text-sm">Add characters and locations first, then create scenes to build your film.</p>
        </div>
      )}
    </div>
  )
}
