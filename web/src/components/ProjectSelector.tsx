import { useState, useEffect, useMemo } from 'react'

const API = '/api'

// Val#2 U1 (operator-validation #2, cycle 10): default render shows the
// top N most-recently-modified projects. At project counts in the
// thousands (operator hit 1844 from pytest leakage), rendering all
// entries is unworkable; the search box + "Show all" toggle make the
// landing page usable at any count. Backend list_projects sorts
// mtime-DESC (closed at the same cycle-10 slice).
const DEFAULT_SHOW_COUNT = 20

interface Props {
  onSelect: (id: string) => void
}

export default function ProjectSelector({ onSelect }: Props) {
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([])
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    fetch(`${API}/projects`).then(r => r.json()).then(setProjects).catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return projects
    return projects.filter(p =>
      p.name.toLowerCase().includes(q) ||
      p.id.toLowerCase().startsWith(q)
    )
  }, [projects, search])

  // When the user is searching, show all matches (don't truncate).
  // When idle, show top N. The toggle button lets them expand.
  const visible = useMemo(
    () =>
      showAll || search.trim()
        ? filtered
        : filtered.slice(0, DEFAULT_SHOW_COUNT),
    [filtered, showAll, search],
  )

  const hiddenCount = filtered.length - visible.length

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
    <div className="min-h-screen bg-editorial-ink flex items-center justify-center">
      {/* Subtle background glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-editorial-brass/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/3 left-1/3 w-[300px] h-[300px] bg-editorial-brass/3 rounded-full blur-[100px]" />
      </div>

      <div className="w-full max-w-lg p-8 relative z-10">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-editorial-ink-rise border border-editorial-rule rounded-full px-4 py-1.5 mb-4">
            <div className="w-2 h-2 rounded-full bg-editorial-brass animate-pulse-slow" />
            <span className="text-eyebrow-lg text-editorial-brass font-medium tracking-widest uppercase">Studio</span>
          </div>
          <h1 className="text-4xl font-bold text-editorial-ivory mb-3 tracking-tight">Cinema Production</h1>
          <p className="text-editorial-ivory-mute text-sm">AI-powered photorealistic cinema with character continuity</p>
        </div>

        {/* Create New */}
        <div className="bg-gradient-panel border border-editorial-rule rounded-2xl p-6 mb-5 shadow-panel">
          <h2 className="text-eyebrow-lg font-semibold text-editorial-brass uppercase tracking-widest mb-4">New Production</h2>
          <div className="flex gap-3">
            <input
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="Enter film title..."
              className="flex-1 bg-editorial-ink border border-editorial-rule rounded-xl px-4 py-2.5 text-editorial-ivory placeholder:text-editorial-ivory-mute/60"
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
          <div className="bg-gradient-panel border border-editorial-rule rounded-2xl p-6 shadow-panel">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="text-eyebrow-lg font-semibold text-editorial-ivory-soft uppercase tracking-widest">
                Recent Productions
              </h2>
              <span className="text-xs text-editorial-ivory-mute font-mono">
                {search.trim()
                  ? `${filtered.length}/${projects.length}`
                  : `${visible.length}/${projects.length}`}
              </span>
            </div>

            {/* Search input */}
            <input
              type="text"
              value={search}
              onChange={e => {
                setSearch(e.target.value)
                if (!e.target.value.trim()) setShowAll(false)
              }}
              placeholder="Search by name or id prefix..."
              aria-label="Search projects"
              className="w-full bg-editorial-ink border border-editorial-rule rounded-xl px-4 py-2 mb-3 text-sm text-editorial-ivory placeholder:text-editorial-ivory-mute/60"
            />

            {/* Project list */}
            <div className="space-y-1.5 max-h-[40vh] overflow-y-auto">
              {visible.map(p => (
                <button
                  key={p.id}
                  onClick={() => onSelect(p.id)}
                  className="w-full text-left px-4 py-3 rounded-xl hover:bg-editorial-ink-rise border border-transparent hover:border-editorial-rule group"
                >
                  <span className="text-editorial-ivory font-medium group-hover:text-editorial-brass transition-colors">{p.name}</span>
                  <span className="text-editorial-ivory-mute text-xs ml-2 font-mono">{p.id.slice(0, 8)}</span>
                </button>
              ))}
            </div>

            {/* Empty state when search yields no matches */}
            {visible.length === 0 && search.trim() && (
              <p className="text-center text-editorial-ivory-mute text-sm py-4">
                No projects match "{search}"
              </p>
            )}

            {/* "Show all" toggle when results are truncated and no search active */}
            {hiddenCount > 0 && !search.trim() && (
              <button
                onClick={() => setShowAll(true)}
                aria-label={`Show all ${projects.length} projects`}
                className="w-full mt-3 text-editorial-brass hover:text-editorial-brass/80 text-sm py-2 border-t border-editorial-rule transition-colors"
              >
                Show all ({projects.length} projects)
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
