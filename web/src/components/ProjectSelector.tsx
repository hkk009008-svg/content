import { useState, useEffect, useMemo, useRef } from 'react'
import { apiDelete, apiGet, apiPost } from '../lib/api'

const API = '/api'

// Val#2 U1 (operator-validation #2, cycle 10): default render shows the
// top N most-recently-modified projects. At project counts in the
// thousands (operator hit 1844 from pytest leakage), rendering all
// entries is unworkable; the search box + "Show all" toggle make the
// landing page usable at any count. Backend list_projects sorts
// mtime-DESC (closed at the same cycle-10 slice).
const DEFAULT_SHOW_COUNT = 20

interface Props {
  /** Resolves only once the full project has loaded. A rejection is rendered
   *  here so selecting an existing project and the create-then-open path
   *  share one accessible failure surface. */
  onSelect: (id: string) => Promise<void>
}

interface ProjectListEntry {
  id: string
  name: string
}

export default function ProjectSelector({ onSelect }: Props) {
  const [projects, setProjects] = useState<ProjectListEntry[]>([])
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [selectingId, setSelectingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [showAll, setShowAll] = useState(false)
  const newNameRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    apiGet<ProjectListEntry[]>(`${API}/projects`).then((result) => {
      if (cancelled) return
      if (result.ok) {
        setProjects(result.data)
      } else {
        setError(result.error)
      }
    })
    return () => { cancelled = true }
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

  const selectProject = async (id: string): Promise<boolean> => {
    setSelectingId(id)
    setError(null)
    try {
      await onSelect(id)
      return true
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Project could not be opened')
      return false
    } finally {
      setSelectingId(null)
    }
  }

  const handleCreate = async () => {
    if (creating || deletingId !== null || selectingId !== null || !newName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const result = await apiPost<ProjectListEntry>(`${API}/projects`, {
        name: newName.trim(),
      })
      if (result.ok) {
        // If opening fails after creation, keep the newly-created project in
        // the list so the operator can retry instead of creating a duplicate.
        setProjects((current) => current.some((item) => item.id === result.data.id)
          ? current
          : [result.data, ...current])
        setNewName('')
        await selectProject(result.data.id)
      } else {
        setError(result.error)
      }
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (project: ProjectListEntry) => {
    if (deletingId !== null || creating || selectingId !== null) return
    const confirmed = window.confirm(
      `Delete “${project.name}”? This removes the project and all of its generated media.`,
    )
    if (!confirmed) return

    setDeletingId(project.id)
    setError(null)
    const result = await apiDelete<{ deleted: boolean }>(
      `${API}/projects/${encodeURIComponent(project.id)}`,
    )
    if (result.ok) {
      const remainingCount = Math.max(projects.length - 1, 0)
      setProjects((current) => current.filter((item) => item.id !== project.id))
      setTimeout(() => {
        if (remainingCount > 0) searchRef.current?.focus()
        else newNameRef.current?.focus()
      }, 0)
    } else {
      setError(result.error)
    }
    setDeletingId(null)
  }

  return (
    <div className="min-h-screen bg-app flex items-center justify-center">
      {/* Subtle background glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-acc/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/3 left-1/3 w-[300px] h-[300px] bg-acc/3 rounded-full blur-[100px]" />
      </div>

      <div className="w-full max-w-lg p-8 relative z-10">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-head border border-line rounded-full px-4 py-1.5 mb-4">
            <div className="w-2 h-2 rounded-full bg-acc animate-pulse-slow" />
            <span className="text-eyebrow-lg text-acc font-medium tracking-widest uppercase">Studio</span>
          </div>
          <h1 className="text-4xl font-bold text-tx mb-3 tracking-tight">Cinema Production</h1>
          <p className="text-mut text-sm">AI-powered photorealistic cinema with character continuity</p>
        </div>

        {/* Create New */}
        <div className="bg-gradient-panel border border-line rounded-2xl p-6 mb-5 shadow-panel">
          <h2 className="text-eyebrow-lg font-semibold text-acc uppercase tracking-widest mb-4">New Production</h2>
          <div className="flex gap-3">
            <input
              ref={newNameRef}
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="Enter film title..."
              aria-label="Film title"
              className="flex-1 bg-app border border-line rounded-xl px-4 py-2.5 text-tx placeholder:text-mut/60"
            />
            <button
              onClick={handleCreate}
              disabled={creating || deletingId !== null || selectingId !== null || !newName.trim()}
              aria-busy={creating}
              className="bg-acc hover:shadow-glow-accent disabled:opacity-30 px-6 py-2.5 rounded-xl text-white font-semibold text-sm shadow-panel"
            >
              {creating ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-fail/50 bg-fail/10 px-4 py-3 text-sm text-tx"
          >
            <span className="font-semibold text-fail">Project action failed:</span> {error}
          </div>
        )}

        {/* Existing Projects */}
        {projects.length > 0 && (
          <div className="bg-gradient-panel border border-line rounded-2xl p-6 shadow-panel">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="text-eyebrow-lg font-semibold text-tx uppercase tracking-widest">
                Recent Productions
              </h2>
              <span className="text-xs text-mut font-mono">
                {search.trim()
                  ? `${filtered.length}/${projects.length}`
                  : `${visible.length}/${projects.length}`}
              </span>
            </div>

            {/* Search input */}
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={e => {
                setSearch(e.target.value)
                if (!e.target.value.trim()) setShowAll(false)
              }}
              placeholder="Search by name or id prefix..."
              aria-label="Search projects"
              className="w-full bg-app border border-line rounded-xl px-4 py-2 mb-3 text-sm text-tx placeholder:text-mut/60"
            />

            {/* Project list */}
            <div className="space-y-1.5 max-h-[40vh] overflow-y-auto">
              {visible.map(p => (
                <div
                  key={p.id}
                  className="group flex items-center rounded-xl border border-transparent hover:border-line hover:bg-head"
                >
                  <button
                    onClick={() => { void selectProject(p.id) }}
                    disabled={deletingId !== null || creating || selectingId !== null}
                    aria-busy={selectingId === p.id}
                    className="min-w-0 flex-1 px-4 py-3 text-left"
                  >
                    <span className="text-tx font-medium group-hover:text-acc transition-colors">{p.name}</span>
                    <span className="text-mut text-xs ml-2 font-mono">{p.id.slice(0, 8)}</span>
                    {selectingId === p.id && <span className="ml-2 text-xs text-acc">Opening…</span>}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(p)}
                    disabled={deletingId !== null || creating || selectingId !== null}
                    aria-label={`Delete ${p.name}`}
                    className="mr-2 rounded border border-transparent px-2 py-1 text-xs text-mut hover:border-fail/50 hover:text-fail disabled:opacity-40"
                  >
                    {deletingId === p.id ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              ))}
            </div>

            {/* Empty state when search yields no matches */}
            {visible.length === 0 && search.trim() && (
              <p className="text-center text-mut text-sm py-4">
                No projects match "{search}"
              </p>
            )}

            {/* "Show all" toggle when results are truncated and no search active */}
            {hiddenCount > 0 && !search.trim() && (
              <button
                onClick={() => setShowAll(true)}
                aria-label={`Show all ${projects.length} projects`}
                className="w-full mt-3 text-acc hover:text-acc/80 text-sm py-2 border-t border-line transition-colors"
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
