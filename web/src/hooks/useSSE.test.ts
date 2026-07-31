import { createElement, startTransition, Suspense } from 'react'
import { act, cleanup, render, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProgressEvent } from '../types/project'
import { useSSE } from './useSSE'

// Slice 11a wire shape: `id`/`replayed` are inlined onto data-bearing events
// (live or reconnect-replayed); GAP/HEARTBEAT/END never carry either.
type WireEvent = ProgressEvent & { id?: number; replayed?: boolean; gap_from?: number; gap_to?: number }

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

  emit(event: WireEvent) {
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

describe('useSSE -- reconnect resumes from the last seen event id (Slice 11b)', () => {
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

  it('a fresh connection carries no last_event_id, then a reconnect after a real event sends it', () => {
    const { result } = renderHook(() => useSSE('A'))

    act(() => result.current.start())
    const first = MockEventSource.instances[0]
    expect(first.url).toBe('/api/projects/A/stream') // no known position yet -- server's own snapshot path

    act(() => first.emit({ ...progressEvent, id: 7 }))
    act(() => first.fail())
    act(() => vi.advanceTimersByTime(1_000))

    const second = MockEventSource.instances[1]
    expect(second.url).toBe('/api/projects/A/stream?last_event_id=7')
  })

  it('the tracked id advances with each further event, so a SECOND reconnect resumes from the newest one', () => {
    const { result } = renderHook(() => useSSE('A'))

    act(() => result.current.start())
    const first = MockEventSource.instances[0]
    act(() => first.emit({ ...progressEvent, id: 3 }))
    act(() => first.fail())
    act(() => vi.advanceTimersByTime(1_000))

    const second = MockEventSource.instances[1]
    expect(second.url).toBe('/api/projects/A/stream?last_event_id=3')
    act(() => second.emit({ ...progressEvent, id: 9, replayed: true }))
    act(() => second.fail())
    act(() => vi.advanceTimersByTime(1_000))

    const third = MockEventSource.instances[2]
    expect(third.url).toBe('/api/projects/A/stream?last_event_id=9')
  })

  it('a GAP control frame flows through into events/latest like a real message (no id, unlike data events)', () => {
    const { result } = renderHook(() => useSSE('A'))
    act(() => result.current.start())
    const source = MockEventSource.instances[0]

    const gapEvent: WireEvent = { stage: 'GAP', detail: 'Missed events 4-9 (replay buffer cap exceeded)', percent: -1, gap_from: 4, gap_to: 9 }
    act(() => source.emit(gapEvent))

    expect(result.current.latest).toEqual(gapEvent)
    expect(result.current.events).toEqual([gapEvent])

    // GAP carries no id -- a reconnect right after it must not claim a
    // position the server never confirmed.
    act(() => source.fail())
    act(() => vi.advanceTimersByTime(1_000))
    expect(MockEventSource.instances[1].url).toBe('/api/projects/A/stream')
  })

  it('starting a fresh run resets the tracked id -- a new run must not send a stale last_event_id from the prior run', () => {
    const { result } = renderHook(() => useSSE('A'))

    act(() => result.current.start())
    const run1 = MockEventSource.instances[0]
    act(() => run1.emit({ ...progressEvent, id: 42 }))
    act(() => run1.emit({ ...progressEvent, stage: 'END' })) // graceful end of run 1

    act(() => result.current.start()) // run 2 begins
    const run2 = MockEventSource.instances[1]
    expect(run2.url).toBe('/api/projects/A/stream') // no last_event_id=42 leaking into a fresh bus
  })

  it('a project switch also resets the tracked id', () => {
    const { result, rerender } = renderHook(
      ({ projectId }) => useSSE(projectId),
      { initialProps: { projectId: 'A' } },
    )
    act(() => result.current.start())
    const sourceA = MockEventSource.instances[0]
    act(() => sourceA.emit({ ...progressEvent, id: 15 }))

    rerender({ projectId: 'B' })
    act(() => result.current.start())
    const sourceB = MockEventSource.instances[1]
    expect(sourceB.url).toBe('/api/projects/B/stream')

    act(() => sourceB.fail())
    act(() => vi.advanceTimersByTime(1_000))
    expect(MockEventSource.instances[2].url).toBe('/api/projects/B/stream') // still no id -- B never saw one
  })
})
