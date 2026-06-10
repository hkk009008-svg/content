import { useState, useEffect, useCallback, useRef } from 'react'
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

export function useSSE(projectId: string | null) {
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [latest, setLatest] = useState<ProgressEvent | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const sourceRef = useRef<EventSource | null>(null)
  const attemptRef = useRef(0)
  const retryTimerRef = useRef<number | null>(null)
  const stoppedRef = useRef(false)

  const clearRetry = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!projectId || stoppedRef.current) return
    const es = new EventSource(`/api/projects/${projectId}/stream`)
    sourceRef.current = es

    es.onmessage = (e) => {
      try {
        const data: ProgressEvent = JSON.parse(e.data)
        // Any real message means the connection is healthy — reset backoff.
        if (data.stage !== 'HEARTBEAT') {
          attemptRef.current = 0
        }
        if (data.stage === 'END') {
          stoppedRef.current = true
          es.close()
          sourceRef.current = null
          setIsStreaming(false)
          return
        }
        if (data.stage !== 'HEARTBEAT') {
          setEvents((prev) => [...prev, data])
          setLatest(data)
        }
      } catch {}
    }

    es.onerror = () => {
      es.close()
      sourceRef.current = null
      // Don't retry after explicit stop, END, or budget exhaustion.
      if (stoppedRef.current) {
        setIsStreaming(false)
        return
      }
      attemptRef.current += 1
      if (attemptRef.current > MAX_ATTEMPTS) {
        console.warn(`[SSE] giving up after ${MAX_ATTEMPTS} reconnect attempts`)
        setIsStreaming(false)
        return
      }
      const delay = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** (attemptRef.current - 1))
      console.warn(`[SSE] reconnect attempt ${attemptRef.current}/${MAX_ATTEMPTS} in ${delay}ms`)
      retryTimerRef.current = window.setTimeout(() => {
        retryTimerRef.current = null
        connect()
      }, delay)
    }
  }, [projectId])

  const start = useCallback(() => {
    if (!projectId || sourceRef.current) return
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
  }, [projectId, connect, clearRetry])

  const stop = useCallback(() => {
    stoppedRef.current = true
    clearRetry()
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
    setIsStreaming(false)
  }, [clearRetry])

  useEffect(() => {
    return () => {
      stoppedRef.current = true
      clearRetry()
      if (sourceRef.current) {
        sourceRef.current.close()
      }
    }
  }, [clearRetry])

  return { events, latest, isStreaming, start, stop }
}
