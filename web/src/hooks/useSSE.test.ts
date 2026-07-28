import { createElement, startTransition, Suspense } from 'react'
import { act, cleanup, render, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProgressEvent } from '../types/project'
import { useSSE } from './useSSE'

class MockEventSource {
  static instances: MockEventSource[] = []

  readonly url: string
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  close = vi.fn()

  constructor(url: string | URL) {
    this.url = String(url)
    MockEventSource.instances.push(this)
  }

  emit(event: ProgressEvent) {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>)
  }

  fail() {
    this.onerror?.(new Event('error'))
  }
}

const progressEvent: ProgressEvent = {
  stage: 'MOTION',
  detail: 'project A is rendering',
  percent: 50,
}

describe('useSSE project lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    cleanup()
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('A -> null clears stale state and cancels the A retry', () => {
    const { result, rerender } = renderHook(
      ({ projectId }) => useSSE(projectId),
      { initialProps: { projectId: 'A' as string | null } },
    )

    act(() => result.current.start())
    const sourceA = MockEventSource.instances[0]
    act(() => sourceA.emit(progressEvent))
    act(() => sourceA.fail())
    expect(sourceA.close).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(1)

    rerender({ projectId: null })

    expect(result.current.events).toEqual([])
    expect(result.current.latest).toBeNull()
    expect(result.current.isStreaming).toBe(false)
    expect(sourceA.close).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)

    act(() => vi.advanceTimersByTime(60_000))
    expect(MockEventSource.instances).toHaveLength(1)
  })

  it('A -> B closes live A once, clears state, and opens one B source', () => {
    const { result, rerender } = renderHook(
      ({ projectId }) => useSSE(projectId),
      { initialProps: { projectId: 'A' } },
    )

    act(() => result.current.start())
    const sourceA = MockEventSource.instances[0]
    const staleStartA = result.current.start
    act(() => sourceA.emit(progressEvent))

    rerender({ projectId: 'B' })

    expect(sourceA.close).toHaveBeenCalledTimes(1)
    expect(result.current.events).toEqual([])
    expect(result.current.latest).toBeNull()
    expect(result.current.isStreaming).toBe(false)

    act(() => result.current.start())
    expect(MockEventSource.instances).toHaveLength(2)
    const sourceB = MockEventSource.instances[1]
    expect(sourceB.url).toBe('/api/projects/B/stream')
    expect(result.current.isStreaming).toBe(true)

    act(() => {
      sourceA.emit({ ...progressEvent, detail: 'stale A event' })
      sourceA.fail()
      staleStartA()
      vi.advanceTimersByTime(60_000)
    })
    expect(sourceA.close).toHaveBeenCalledTimes(1)
    expect(sourceB.close).not.toHaveBeenCalled()
    expect(MockEventSource.instances).toHaveLength(2)
    expect(result.current.events).toEqual([])
    expect(result.current.latest).toBeNull()
  })

  it('A -> B cancels a queued A reconnect before B starts', () => {
    const { result, rerender } = renderHook(
      ({ projectId }) => useSSE(projectId),
      { initialProps: { projectId: 'A' } },
    )

    act(() => result.current.start())
    const sourceA = MockEventSource.instances[0]
    act(() => sourceA.fail())
    expect(vi.getTimerCount()).toBe(1)

    rerender({ projectId: 'B' })
    expect(vi.getTimerCount()).toBe(0)
    act(() => result.current.start())
    const sourceB = MockEventSource.instances[1]

    act(() => vi.advanceTimersByTime(60_000))
    expect(sourceA.close).toHaveBeenCalledTimes(1)
    expect(sourceB.close).not.toHaveBeenCalled()
    expect(MockEventSource.instances).toHaveLength(2)
  })

  it('unmount closes the active source without post-unmount updates', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { result, unmount } = renderHook(() => useSSE('A'))

    act(() => result.current.start())
    const sourceA = MockEventSource.instances[0]
    unmount()

    expect(sourceA.close).toHaveBeenCalledTimes(1)
    act(() => {
      sourceA.emit(progressEvent)
      sourceA.fail()
      vi.runAllTimers()
    })
    expect(sourceA.close).toHaveBeenCalledTimes(1)
    expect(MockEventSource.instances).toHaveLength(1)
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('explicit stop clears retry and suppresses reconnect', () => {
    const { result } = renderHook(() => useSSE('A'))

    act(() => result.current.start())
    const sourceA = MockEventSource.instances[0]
    act(() => sourceA.emit(progressEvent))
    act(() => sourceA.fail())
    expect(vi.getTimerCount()).toBe(1)

    act(() => result.current.stop())
    expect(result.current.isStreaming).toBe(false)
    expect(result.current.events).toEqual([progressEvent])
    expect(result.current.latest).toEqual(progressEvent)
    expect(vi.getTimerCount()).toBe(0)

    act(() => vi.advanceTimersByTime(60_000))
    expect(sourceA.close).toHaveBeenCalledTimes(1)
    expect(MockEventSource.instances).toHaveLength(1)
  })

  it('preserves exponential retry delays and resets backoff after a message', () => {
    const { result } = renderHook(() => useSSE('A'))

    act(() => result.current.start())
    const first = MockEventSource.instances[0]
    act(() => first.fail())

    act(() => vi.advanceTimersByTime(999))
    expect(MockEventSource.instances).toHaveLength(1)
    act(() => vi.advanceTimersByTime(1))
    const second = MockEventSource.instances[1]

    act(() => second.fail())
    act(() => vi.advanceTimersByTime(1_999))
    expect(MockEventSource.instances).toHaveLength(2)
    act(() => vi.advanceTimersByTime(1))
    const third = MockEventSource.instances[2]

    act(() => third.emit(progressEvent))
    act(() => third.fail())
    act(() => vi.advanceTimersByTime(999))
    expect(MockEventSource.instances).toHaveLength(3)
    act(() => vi.advanceTimersByTime(1))
    expect(MockEventSource.instances).toHaveLength(4)
  })

  it('same-project rerender leaves a live source and event state intact', () => {
    const { result, rerender } = renderHook(
      ({ projectId }) => useSSE(projectId),
      { initialProps: { projectId: 'A' } },
    )

    act(() => result.current.start())
    const sourceA = MockEventSource.instances[0]
    act(() => sourceA.emit(progressEvent))

    rerender({ projectId: 'A' })
    act(() => result.current.start())

    expect(sourceA.close).not.toHaveBeenCalled()
    expect(MockEventSource.instances).toHaveLength(1)
    expect(result.current.events).toEqual([progressEvent])
    expect(result.current.latest).toEqual(progressEvent)
    expect(result.current.isStreaming).toBe(true)
  })

  it('an interrupted B render cannot poison the committed A connection', () => {
    type SSEState = ReturnType<typeof useSSE>
    let committedState: SSEState | null = null
    let attemptedBRender = false
    const suspendedForever = new Promise<never>(() => {})

    function Probe({ projectId }: { projectId: string }) {
      const state = useSSE(projectId)
      if (projectId === 'B') {
        attemptedBRender = true
        throw suspendedForever
      }
      committedState = state
      return null
    }

    const tree = (projectId: string) => createElement(
      Suspense,
      { fallback: null },
      createElement(Probe, { projectId }),
    )
    const view = render(tree('A'))

    act(() => committedState!.start())
    const sourceA = MockEventSource.instances[0]

    act(() => {
      startTransition(() => view.rerender(tree('B')))
    })
    expect(attemptedBRender).toBe(true)
    act(() => sourceA.emit({ ...progressEvent, detail: 'committed A event' }))

    expect(committedState!.latest?.detail).toBe('committed A event')
    expect(sourceA.close).not.toHaveBeenCalled()

    act(() => sourceA.fail())
    expect(sourceA.close).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(1)

    act(() => vi.advanceTimersByTime(1_000))
    expect(MockEventSource.instances).toHaveLength(2)
    expect(MockEventSource.instances[1].url).toBe('/api/projects/A/stream')
  })
})
