import { useId, useRef, useState } from 'react'
import { apiRequest } from '../../lib/api'

interface Props {
  projectId: string
  shotId: string
  hasDrivingVideo: boolean
  onUploaded: () => Promise<void> | void
  compact?: boolean
  disabled?: boolean
  onBusyChange?: (busy: boolean) => void
}

interface UploadResponse {
  uploaded?: boolean
  unchanged?: boolean
  path?: string
  requires_performance_regeneration?: boolean
}

export default function DrivingVideoUploadControl({
  projectId,
  shotId,
  hasDrivingVideo,
  onUploaded,
  compact = false,
  disabled = false,
  onBusyChange,
}: Props) {
  const inputId = useId()
  const feedbackId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [feedback, setFeedback] = useState<{
    kind: 'status' | 'error'
    message: string
  } | null>(null)

  const upload = async (file: File) => {
    setUploading(true)
    onBusyChange?.(true)
    setFeedback(null)
    const form = new FormData()
    form.append('driving_video', file)
    const result = await apiRequest<UploadResponse>(
      `/api/projects/${projectId}/shots/${shotId}/upload-driving-video`,
      { method: 'POST', body: form },
    )

    if (!result.ok) {
      setFeedback({ kind: 'error', message: result.error })
      setUploading(false)
      onBusyChange?.(false)
      if (inputRef.current) inputRef.current.value = ''
      return
    }
    if (result.data?.uploaded !== true || typeof result.data.path !== 'string') {
      setFeedback({
        kind: 'error',
        message: 'The server did not confirm the driving-video upload.',
      })
      setUploading(false)
      onBusyChange?.(false)
      if (inputRef.current) inputRef.current.value = ''
      return
    }

    try {
      if (result.data.requires_performance_regeneration === true) {
        try {
          window.sessionStorage.removeItem(
            `cinema:performance-request:${projectId}:${shotId}`,
          )
        } catch {
          // The server-side revision binding remains authoritative when
          // browser storage is unavailable.
        }
      }
      await onUploaded()
      setFeedback({
        kind: 'status',
        message: result.data.requires_performance_regeneration === false
          ? result.data.unchanged === true
            ? 'This driving video is already selected; approvals were unchanged.'
            : 'Driving video uploaded.'
          : 'Driving video uploaded. Generate and approve a new performance take.',
      })
    } catch (error) {
      setFeedback({
        kind: 'error',
        message: `Driving video uploaded, but project refresh failed: ${
          error instanceof Error && error.message ? error.message : 'Unknown error'
        }`,
      })
    } finally {
      setUploading(false)
      onBusyChange?.(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const buttonLabel = uploading
    ? 'Uploading driving video…'
    : hasDrivingVideo
      ? 'Replace driving video'
      : 'Upload driving video'

  return (
    <div className={compact ? 'inline-flex flex-col items-start' : 'flex flex-col items-start'}>
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        accept="video/*"
        className="sr-only"
        aria-label={`Driving video file for shot ${shotId}`}
        aria-describedby={feedback ? feedbackId : undefined}
        disabled={disabled || uploading}
        tabIndex={-1}
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) void upload(file)
        }}
      />
      <button
        type="button"
        disabled={disabled || uploading}
        aria-busy={uploading}
        aria-controls={inputId}
        aria-describedby={feedback ? feedbackId : undefined}
        onClick={() => inputRef.current?.click()}
        className={compact
          ? 'text-eyebrow-sm text-acc underline hover:text-acc disabled:cursor-not-allowed disabled:opacity-40'
          : 'rounded border border-acc/50 px-2 py-1 text-eyebrow-lg text-acc hover:bg-acc/10 disabled:cursor-not-allowed disabled:opacity-40'}
      >
        {buttonLabel}
      </button>
      {feedback && (
        <p
          id={feedbackId}
          role={feedback.kind === 'error' ? 'alert' : 'status'}
          className={`mt-1 max-w-72 text-[10px] leading-tight ${
            feedback.kind === 'error' ? 'text-fail' : 'text-ok'
          }`}
        >
          {feedback.message}
        </p>
      )}
    </div>
  )
}
