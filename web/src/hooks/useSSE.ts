import { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react'
import type { ProgressEvent } from '../types/project'

// Bundle-C 3.1 (2026-05-24): exponential-backoff reconnect.
// Pipeline runs are 30+ minutes; a momentary network blip used to drop the
// operator's progress feed permanently. The pipeline keeps running on the
// server (predicate-poll gates survive disconnects, see ARCHITECTURE.md §6),
// but the UI was blind until manual refresh. Now we retry up to MAX_ATTEMPTS
// with 1s -> 2s -> 4s -> 8s -> ... capped at MAX_DELAY_MS. A clean END event
// or a stop() call disables retry. Successful event reception resets the
// attempt counter so transient blips don't burn the retry budget over time.
const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 30_000
const MAX_ATTEMPTS = 10
const NO_EVENTS: ProgressEvent[] = []

export function useSSE(projectId: string | null) {
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [latest, setLatest] = useState<ProgressEvent | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const sourceRef = useRef<EventSource | null>(null)
  const attemptRef = useRef(0)
  const retryTimerRef = useRef<number | null>(null)
  const stoppedRef = useRef(false)
  const mountedRef = useRef(true)
  const generationRef = useRef(0)
  const activeProjectRef = useRef<string | null>(projectId)
  const committedProjectRef = useRef<string | null>(projectId)
  const closedSourcesRef = useRef<WeakSet<EventSource>>(new WeakSet())

  const clearRetry = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }, [])

  const closeSource = useCallback((source: EventSource) => {
    if (closedSourcesRef.current.has(source)) return
    closedSourcesRef.current.add(source)
    source.close()
  }, [])

  const closeAndReset = useCallback((
    clearEventState: boolean,
    updateState = true,
  ) => {
    generationRef.current += 1
    clearRetry()
    const source = sourceRef.current
    sourceRef.current = null
    if (source) closeSource(source)
    attemptRef.current = 0

    if (clearEventState) {
      if (updateState && mountedRef.current) {
        setEvents([])
        setLatest(null)
      }
    }
    if (updateState && mountedRef.current) {
      setIsStreaming(false)
    }
  }, [clearRetry, closeSource])

  const syncProject = useCallback((nextProjectId: string | null) => {
    if (activeProjectRef.current === nextProjectId) return
    closeAndReset(true)
    activeProjectRef.current = nextProjectId
    stoppedRef.current = false
  }, [closeAndReset])

  const connect = useCallback(() => {
    if (
      !mountedRef.current
      || !projectId
      || committedProjectRef.current !== projectId
      || activeProjectRef.current !== projectId
      || stoppedRef.current
      || sourceRef.current
    ) return

    const connectionGeneration = generationRef.current
    const es = new EventSource(`/api/projects/${projectId}/stream`)
    sourceRef.current = es

    const isCurrentConnection = () => (
      mountedRef.current
      && generationRef.current === connectionGeneration
      && committedProjectRef.current === projectId
      && activeProjectRef.current === projectId
      && sourceRef.current === es
    )

    es.onmessage = (e) => {
      if (!isCurrentConnection()) return
      try {
        const data: ProgressEvent = JSON.parse(e.data)
        // Any real message means the connection is healthy — reset backoff.
        if (data.stage !== 'HEARTBEAT') {
          attemptRef.current = 0
        }
        if (data.stage === 'END') {
          stoppedRef.current = true
          closeAndReset(false)
          return
        }
        if (data.stage !== 'HEARTBEAT') {
          setEvents((prev) => [...prev, data])
          setLatest(data)
        }
      } catch {}
    }

    es.onerror = () => {
      if (!isCurrentConnection()) {
        closeSource(es)
        return
      }
      closeSource(es)
      sourceRef.current = null
      // Don't retry after explicit stop, END, or budget exhaustion.
      if (stoppedRef.current) {
        if (mountedRef.current) setIsStreaming(false)
        return
      }
      attemptRef.current += 1
      if (attemptRef.current > MAX_ATTEMPTS) {
        console.warn(`[SSE] giving up after ${MAX_ATTEMPTS} reconnect attempts`)
        if (mountedRef.current) setIsStreaming(false)
        return
      }
      const delay = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** (attemptRef.current - 1))
      console.warn(`[SSE] reconnect attempt ${attemptRef.current}/${MAX_ATTEMPTS} in ${delay}ms`)
      const timerId = window.setTimeout(() => {
        if (retryTimerRef.current !== timerId) return
        retryTimerRef.current = null
        if (
          !mountedRef.current
          || generationRef.current !== connectionGeneration
          || committedProjectRef.current !== projectId
          || activeProjectRef.current !== projectId
          || stoppedRef.current
        ) return
        connect()
      }, delay)
      retryTimerRef.current = timerId
    }
  }, [projectId, closeAndReset, closeSource])

  const start = useCallback(() => {
    if (
      !mountedRef.current
      || !projectId
      || committedProjectRef.current !== projectId
    ) return
    syncProject(projectId)
    if (sourceRef.current) return
    clearRetry()
    setEvents([])
    // Without this, the previous run's last event (stage/detail/engine)
    // leaks into the new run's UI until the first event arrives — e.g. a
    // stale 'VIA <engine>' marquee fragment after a cancel (wf_9877b1d1).
    setLatest(null)
    setIsStreaming(true)
    attemptRef.current = 0
    stoppedRef.current = false
    connect()
  }, [projectId, connect, clearRetry, syncProject])

  const stop = useCallback(() => {
    stoppedRef.current = true
    closeAndReset(false)
  }, [closeAndReset])

  useLayoutEffect(() => {
    committedProjectRef.current = projectId
    syncProject(projectId)
  }, [projectId, syncProject])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      stoppedRef.current = true
      closeAndReset(false, false)
    }
  }, [closeAndReset])

  const projectStateIsCurrent = activeProjectRef.current === projectId
  return {
    events: projectStateIsCurrent ? events : NO_EVENTS,
    latest: projectStateIsCurrent ? latest : null,
    isStreaming: projectStateIsCurrent ? isStreaming : false,
    start,
    stop,
  }
}
