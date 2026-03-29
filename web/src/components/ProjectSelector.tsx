import { useState, useEffect } from 'react'

const API = '/api'

interface Props {
  onSelect: (id: string) => void
}

export default function ProjectSelector({ onSelect }: Props) {
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([])
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    fetch(`${API}/projects`).then(r => r.json()).then(setProjects).catch(() => {})
  }, [])

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    const res = await fetch(`${API}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim() }),
    })
    if (res.ok) {
      const project = await res.json()
      onSelect(project.id)
    }
    setCreating(false)
  }

  return (
    <div className="min-h-screen bg-cinema-bg flex items-center justify-center">
      {/* Subtle background glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-cinema-accent/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/3 left-1/3 w-[300px] h-[300px] bg-cinema-gold/3 rounded-full blur-[100px]" />
      </div>

      <div className="w-full max-w-lg p-8 relative z-10">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-cinema-panel-elevated border border-cinema-border-subtle rounded-full px-4 py-1.5 mb-4">
            <div className="w-2 h-2 rounded-full bg-cinema-gold animate-pulse-slow" />
            <span className="text-[11px] text-cinema-gold font-medium tracking-widest uppercase">Studio</span>
          </div>
          <h1 className="text-4xl font-bold text-cinema-text mb-3 tracking-tight">Cinema Production</h1>
          <p className="text-cinema-muted text-sm">AI-powered photorealistic cinema with character continuity</p>
        </div>

        {/* Create New */}
        <div className="bg-gradient-panel border border-cinema-border-subtle rounded-2xl p-6 mb-5 shadow-panel">
          <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest mb-4">New Production</h2>
          <div className="flex gap-3">
            <input
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="Enter film title..."
              className="flex-1 bg-cinema-bg border border-cinema-border rounded-xl px-4 py-2.5 text-cinema-text placeholder:text-cinema-muted/60"
            />
            <button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
              className="bg-gradient-accent hover:shadow-glow-accent disabled:opacity-30 px-6 py-2.5 rounded-xl text-white font-semibold text-sm shadow-panel"
            >
              {creating ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>

        {/* Existing Projects */}
        {projects.length > 0 && (
          <div className="bg-gradient-panel border border-cinema-border-subtle rounded-2xl p-6 shadow-panel">
            <h2 className="text-[11px] font-semibold text-cinema-text-secondary uppercase tracking-widest mb-4">Recent Productions</h2>
            <div className="space-y-1.5">
              {projects.map(p => (
                <button
                  key={p.id}
                  onClick={() => onSelect(p.id)}
                  className="w-full text-left px-4 py-3 rounded-xl hover:bg-cinema-panel-hover border border-transparent hover:border-cinema-border-subtle group"
                >
                  <span className="text-cinema-text font-medium group-hover:text-cinema-gold transition-colors">{p.name}</span>
                  <span className="text-cinema-muted text-xs ml-2 font-mono">{p.id.slice(0, 8)}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
