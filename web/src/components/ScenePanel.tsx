import { useState } from 'react'
import type { Project, AppConfig, Scene } from '../types/project'

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

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-cinema-muted uppercase tracking-wider">
          Scene Timeline ({project.scenes.length} scenes)
        </h2>
        <button onClick={() => setAdding(true)}
          className="bg-cinema-accent hover:bg-cinema-accent2 px-3 py-1.5 rounded text-white text-xs font-medium">
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
            className={`bg-cinema-panel border rounded-lg overflow-hidden transition-all ${
              dragOverId === scene.id ? 'border-cinema-accent ring-1 ring-cinema-accent/50' :
              draggedId === scene.id ? 'opacity-50 border-cinema-border' : 'border-cinema-border'
            }`}
          >
            {/* Scene Header */}
            <div
              className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-cinema-bg/50"
              onClick={() => setEditing(editing === scene.id ? null : scene.id)}
            >
              <div className="flex items-center gap-3">
                <span className="text-cinema-muted text-xs font-mono w-6">{idx + 1}</span>
                <div>
                  <div className="text-cinema-text text-sm font-medium">{scene.title}</div>
                  <div className="text-cinema-muted text-xs mt-0.5">
                    {scene.characters_present.length} chars
                    {scene.location_id && ` / ${project.locations.find(l => l.id === scene.location_id)?.name || 'Unknown'}`}
                    {' / '}{scene.duration_seconds}s
                    {scene.num_shots > 0 && ` / ${scene.num_shots} shots`}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-2 py-0.5 rounded ${scene.mood === 'tense' ? 'bg-red-900/30 text-red-400' : scene.mood === 'melancholic' ? 'bg-blue-900/30 text-blue-400' : 'bg-cinema-bg text-cinema-muted'}`}>
                  {scene.mood}
                </span>
                <button onClick={e => { e.stopPropagation(); handleDelete(scene.id) }}
                  className="text-cinema-muted hover:text-cinema-danger text-xs">X</button>
              </div>
            </div>

            {/* Expanded Editor */}
            {editing === scene.id && (
              <div className="border-t border-cinema-border px-4 py-3 space-y-3 bg-cinema-bg/30">
                <div className="text-xs text-cinema-muted line-clamp-2">{scene.action}</div>

                {/* Action */}
                <div>
                  <label className="text-xs text-cinema-muted block mb-1">Action / What happens</label>
                  <textarea
                    defaultValue={scene.action}
                    onBlur={e => handleUpdate(scene.id, { action: e.target.value })}
                    rows={2} placeholder="Describe what happens in this scene..."
                    className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent resize-none"
                  />
                </div>

                {/* Dialogue */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs text-cinema-muted">Dialogue</label>
                    <button onClick={() => handleGenerateDialogue(scene.id)}
                      disabled={generatingDialogue === scene.id}
                      className="text-[10px] text-cinema-accent hover:text-cinema-accent2">
                      {generatingDialogue === scene.id ? 'Generating...' : 'Auto-generate'}
                    </button>
                  </div>
                  <textarea
                    defaultValue={scene.dialogue}
                    onBlur={e => handleUpdate(scene.id, { dialogue: e.target.value })}
                    rows={3} placeholder="Character Name: dialogue line..."
                    className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent resize-none font-mono text-xs"
                  />
                </div>

                {/* Characters in scene */}
                <div>
                  <label className="text-xs text-cinema-muted block mb-1">Characters in scene</label>
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
                          className={`px-2 py-1 rounded text-xs ${active ? 'bg-cinema-accent text-white' : 'bg-cinema-panel text-cinema-muted border border-cinema-border'}`}>
                          {c.name}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Location + Mood + Duration row */}
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-xs text-cinema-muted block mb-1">Location</label>
                    <select
                      value={scene.location_id}
                      onChange={e => handleUpdate(scene.id, { location_id: e.target.value })}
                      className="w-full bg-cinema-panel border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text">
                      <option value="">None</option>
                      {project.locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-cinema-muted block mb-1">Mood</label>
                    <select
                      value={scene.mood}
                      onChange={e => handleUpdate(scene.id, { mood: e.target.value })}
                      className="w-full bg-cinema-panel border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text">
                      {(config?.mood_options || ['cinematic', 'melancholic', 'tense', 'hopeful', 'dark']).map(m =>
                        <option key={m} value={m}>{m}</option>
                      )}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-cinema-muted block mb-1">Duration (s)</label>
                    <input type="number" min={2} max={30} step={0.5}
                      value={scene.duration_seconds}
                      onChange={e => handleUpdate(scene.id, { duration_seconds: parseFloat(e.target.value) })}
                      className="w-full bg-cinema-panel border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text" />
                  </div>
                </div>

                {/* Camera direction */}
                <div>
                  <label className="text-xs text-cinema-muted block mb-1">Camera direction (optional — AI will decide if blank)</label>
                  <input type="text"
                    defaultValue={scene.camera_direction}
                    onBlur={e => handleUpdate(scene.id, { camera_direction: e.target.value })}
                    placeholder="e.g., Start ECU on hands, pull back to wide, dolly right to reveal..."
                    className="w-full bg-cinema-panel border border-cinema-border rounded px-3 py-2 text-xs text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent" />
                </div>

                {/* Shot breakdown preview */}
                {scene.shots && scene.shots.length > 0 && (
                  <div>
                    <label className="text-xs text-cinema-muted block mb-1">Shot Breakdown ({scene.shots.length} shots)</label>
                    <div className="space-y-1">
                      {scene.shots.map((shot, si) => (
                        <div key={shot.id || si} className="bg-cinema-panel rounded px-2 py-1.5 text-[10px] text-cinema-muted flex gap-2">
                          <span className="text-cinema-accent font-mono">{si + 1}</span>
                          <span className="flex-1 line-clamp-1">{shot.prompt?.slice(0, 80)}...</span>
                          <span className="text-cinema-muted">{shot.camera}</span>
                          <span className="text-cinema-muted">{shot.target_api}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <button onClick={() => handleDecompose(scene.id)}
                  className="w-full border border-cinema-accent/40 hover:bg-cinema-accent/10 rounded py-1.5 text-cinema-accent text-xs">
                  {scene.shots?.length ? 'Re-decompose into shots' : 'Decompose into shots'}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Add Scene Form */}
      {adding && (
        <div className="mt-4 bg-cinema-panel border border-cinema-accent/30 rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-medium text-cinema-text">New Scene</h3>
          <input type="text" placeholder="Scene title" value={form.title}
            onChange={e => setForm({ ...form, title: e.target.value })}
            className="w-full bg-cinema-bg border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent" />
          <textarea placeholder="What happens in this scene..."
            value={form.action} onChange={e => setForm({ ...form, action: e.target.value })}
            rows={2} className="w-full bg-cinema-bg border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent resize-none" />
          <textarea placeholder="Dialogue (optional — can auto-generate later)"
            value={form.dialogue} onChange={e => setForm({ ...form, dialogue: e.target.value })}
            rows={2} className="w-full bg-cinema-bg border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted focus:outline-none focus:border-cinema-accent resize-none font-mono text-xs" />
          <div>
            <label className="text-xs text-cinema-muted block mb-1">Characters</label>
            <div className="flex flex-wrap gap-1">
              {project.characters.map(c => (
                <button key={c.id} onClick={() => toggleCharacter(c.id)}
                  className={`px-2 py-1 rounded text-xs ${form.characters_present.includes(c.id) ? 'bg-cinema-accent text-white' : 'bg-cinema-bg text-cinema-muted border border-cinema-border'}`}>
                  {c.name}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <select value={form.location_id} onChange={e => setForm({ ...form, location_id: e.target.value })}
              className="bg-cinema-bg border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text">
              <option value="">Location...</option>
              {project.locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
            <select value={form.mood} onChange={e => setForm({ ...form, mood: e.target.value })}
              className="bg-cinema-bg border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text">
              {(config?.mood_options || ['cinematic']).map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <input type="number" min={2} max={30} step={0.5} value={form.duration_seconds}
              onChange={e => setForm({ ...form, duration_seconds: e.target.value })}
              className="bg-cinema-bg border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text" placeholder="Duration (s)" />
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdd} disabled={!form.title.trim()}
              className="flex-1 bg-cinema-accent hover:bg-cinema-accent2 disabled:opacity-40 py-2 rounded text-white text-sm font-medium">
              Add Scene
            </button>
            <button onClick={() => setAdding(false)} className="px-4 py-2 text-cinema-muted text-sm">Cancel</button>
          </div>
        </div>
      )}

      {project.scenes.length === 0 && !adding && (
        <div className="text-center py-12 text-cinema-muted">
          <div className="text-2xl mb-2">No scenes yet</div>
          <p className="text-sm">Add characters and locations first, then create scenes to build your film.</p>
        </div>
      )}
    </div>
  )
}
