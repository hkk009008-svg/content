import { createContext, useContext, useState, type ReactNode } from 'react'

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

export type Page = 'setup' | 'edit' | 'run' | 'capability'

export interface PageContextValue {
  page: Page
  setPage: (page: Page) => void
  /** Scene id the Edit page should focus (Task 6). `null` = no focus. */
  focusScene: string | null
  setFocusScene: (id: string | null) => void
}

const PageContext = createContext<PageContextValue | null>(null)

export function PageProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>('setup')
  const [focusScene, setFocusScene] = useState<string | null>(null)
  return (
    <PageContext.Provider value={{ page, setPage, focusScene, setFocusScene }}>
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
