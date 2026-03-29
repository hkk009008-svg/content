import { useState, useEffect, useCallback, useRef } from 'react'
import type { ProgressEvent } from '../types/project'

export function useSSE(projectId: string | null) {
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [latest, setLatest] = useState<ProgressEvent | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const sourceRef = useRef<EventSource | null>(null)

  const start = useCallback(() => {
    if (!projectId || sourceRef.current) return

    setEvents([])
    setIsStreaming(true)

    const es = new EventSource(`/api/projects/${projectId}/stream`)
    sourceRef.current = es

    es.onmessage = (e) => {
      try {
        const data: ProgressEvent = JSON.parse(e.data)
        if (data.stage === 'END') {
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
      setIsStreaming(false)
    }
  }, [projectId])

  const stop = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
    setIsStreaming(false)
  }, [])

  useEffect(() => {
    return () => {
      if (sourceRef.current) {
        sourceRef.current.close()
      }
    }
  }, [])

  return { events, latest, isStreaming, start, stop }
}
