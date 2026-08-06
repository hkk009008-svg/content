import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PageProvider, usePage } from './PageContext'

describe('PageContext', () => {
  it('throws when used outside a PageProvider', () => {
    // Swallow the expected React error-boundary console noise for this
    // one assertion (renderHook has no boundary of its own).
    expect(() => renderHook(() => usePage())).toThrow('usePage must be used within a <PageProvider>')
  })

  it('defaults to the Setup page with no scene focused', () => {
    const { result } = renderHook(() => usePage(), { wrapper: PageProvider })
    expect(result.current.page).toBe('setup')
    expect(result.current.focusScene).toBeNull()
  })

  it('setPage / setFocusScene update independently', () => {
    const { result } = renderHook(() => usePage(), { wrapper: PageProvider })

    act(() => result.current.setPage('edit'))
    expect(result.current.page).toBe('edit')
    expect(result.current.focusScene).toBeNull() // unaffected

    act(() => result.current.setFocusScene('scene-42'))
    expect(result.current.focusScene).toBe('scene-42')
    expect(result.current.page).toBe('edit') // unaffected

    act(() => result.current.setPage('identity'))
    expect(result.current.page).toBe('identity')
    expect(result.current.focusScene).toBe('scene-42')
  })

  it('resetForNewProject() resets page to Setup and clears focusScene (Slice 8b PID boundary)', () => {
    const { result } = renderHook(() => usePage(), { wrapper: PageProvider })

    act(() => {
      result.current.setPage('run')
      result.current.setFocusScene('scene-from-project-a')
    })
    expect(result.current.page).toBe('run')
    expect(result.current.focusScene).toBe('scene-from-project-a')

    act(() => result.current.resetForNewProject())

    expect(result.current.page).toBe('setup')
    expect(result.current.focusScene).toBeNull()
  })
})
