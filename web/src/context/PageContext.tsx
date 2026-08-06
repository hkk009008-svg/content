import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

/**
 * PageContext — the single source of truth for which top-level page the
 * unified `AppShell` is showing, replacing the old four-`mode` router in
 * `App.tsx`. One persistent shell + a bottom page-bar switch on `page`.
 *
 * `focusScene` is reserved for Task 6 (Edit page "jump to scene"): the
 * page-bar / scene-jump affordances set it so the Edit page can scroll a
 * particular scene into view. It is plumbed here now so later tasks need
 * not touch the provider again.
 */

export type Page = 'setup' | 'edit' | 'run' | 'identity' | 'capability'

export interface PageContextValue {
  page: Page
  setPage: (page: Page) => void
  /** Scene id the Edit page should focus (Task 6). `null` = no focus. */
  focusScene: string | null
  setFocusScene: (id: string | null) => void
  /** Slice 8b (2026-07-30 comprehensive-unification plan): call when the
   *  active project changes. `page`/`focusScene` are otherwise NEVER reset
   *  on their own — `AppInner` never unmounts across a project switch — so
   *  without this, project B would open on whatever page project A left
   *  open, with project A's `focusScene` id still set (scene ids are
   *  project-scoped strings that can collide across projects, so a stale
   *  focus can scroll the wrong scene into view). Resets to the Setup page
   *  with no scene focused. */
  resetForNewProject: () => void
}

const PageContext = createContext<PageContextValue | null>(null)

export function PageProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>('setup')
  const [focusScene, setFocusScene] = useState<string | null>(null)
  const resetForNewProject = useCallback(() => {
    setPage('setup')
    setFocusScene(null)
  }, [])
  return (
    <PageContext.Provider value={{ page, setPage, focusScene, setFocusScene, resetForNewProject }}>
      {children}
    </PageContext.Provider>
  )
}

export function usePage(): PageContextValue {
  const ctx = useContext(PageContext)
  if (!ctx) {
    throw new Error('usePage must be used within a <PageProvider>')
  }
  return ctx
}
