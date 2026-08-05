import { Section, Badge } from '../../ui'
import type { AppConfig, GpuWorkerStatus } from '../../../types/project'

interface Props {
  s: any
  config: AppConfig | null
  imageWorker: GpuWorkerStatus | null
  update: (key: string, value: any) => void | Promise<void>
}

/**
 * Image backend selection. Local FLUX.2 is enabled only by the server's live,
 * hash-bound readiness projection; the browser never derives readiness from
 * endpoint reachability or static candidate metadata.
 */
export function ImageSection({ s, config, imageWorker, update }: Props) {
  const storedBackend: string = s.identity_backend ?? 'gemini_multiref'
  const backend = storedBackend === 'local_flux2_klein'
    ? storedBackend
    : storedBackend === 'gemini_multiref'
      ? storedBackend
      : ''
  const candidate = config?.flux2_candidate
  const localReady = Boolean(
    imageWorker?.state === 'ready'
    && imageWorker.startup_ready === true
    && imageWorker.execution_proven === true
    && imageWorker.benchmark_state === 'passed',
  )
  const localState = imageWorker?.state ?? candidate?.state ?? 'offline'
  const localReason = imageWorker?.message
    || candidate?.reason
    || 'Local worker readiness is unavailable; selection remains disabled.'

  return (
    <Section title="Image">
      <fieldset className="space-y-3">
        <legend className="sr-only">Image generation backend</legend>

        <label className="flex cursor-pointer items-start gap-2 rounded border border-line bg-panel px-2 py-2 focus-within:border-acc">
          <input
            type="radio"
            name="image-backend"
            value="gemini_multiref"
            checked={backend === 'gemini_multiref'}
            onChange={() => update('identity_backend', 'gemini_multiref')}
            className="mt-0.5 accent-acc"
          />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-tx">Nano Banana (Gemini multi-reference)</span>
              <Badge variant="cloud">Cloud</Badge>
              <Badge variant="pri">Default</Badge>
            </span>
            <span className="mt-1 block text-[10px] leading-tight text-mut">
              Uses the configured Gemini image API, then only supported guarded fallbacks.
            </span>
          </span>
        </label>

        <label className={`flex items-start gap-2 rounded border border-line bg-panel px-2 py-2 ${localReady ? 'cursor-pointer focus-within:border-acc' : 'cursor-not-allowed opacity-80'}`}>
          <input
            type="radio"
            name="image-backend"
            value="local_flux2_klein"
            checked={backend === 'local_flux2_klein'}
            disabled={!localReady}
            aria-describedby="local-flux2-readiness"
            onChange={() => update('identity_backend', 'local_flux2_klein')}
            className="mt-0.5 accent-acc"
          />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-tx">
                {candidate?.label || 'Local FLUX.2 Klein 4B'}
              </span>
              <Badge variant="local">Local</Badge>
              <Badge variant={localReady ? 'ok' : 'warn'}>{localState.replace(/_/g, ' ')}</Badge>
            </span>
            <span id="local-flux2-readiness" className="mt-1 block text-[10px] leading-tight text-mut">
              {localReason}
            </span>
            <span className="mt-1 block font-mono text-[10px] leading-tight text-mut">
              benchmark={imageWorker?.benchmark_state || candidate?.benchmark_state || 'unknown'} · blocker={imageWorker?.blocker_code || candidate?.blocker_code || 'worker_status_unavailable'}
            </span>
          </span>
        </label>

        {!backend && (
          <div role="alert" className="rounded border border-fail/50 bg-fail/[0.04] px-2 py-2 text-[10px] leading-4 text-fail">
            This project stores an unsupported image backend. Select a supported backend before running.
          </div>
        )}
      </fieldset>
    </Section>
  )
}
