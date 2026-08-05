import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AppConfig, GpuWorkerStatus } from '../../../types/project'
import { expectNoAxeViolations } from '../../../test/a11y-setup'
import { ImageSection } from './ImageSection'

const CANDIDATE_CONFIG = {
  flux2_candidate: {
    label: 'Local FLUX.2 Klein 4B',
    state: 'not_installed',
    selectable: false,
    startup_ready: false,
    execution_proven: false,
    benchmark_state: 'not_run',
    blocker_code: 'candidate_artifacts_not_installed',
    reason: 'Candidate artifacts are not installed on the Windows worker.',
    license_state: 'official_sources_selected_derivation_pending',
    license_blocker_code: 'qwen_official_shard_derivation_not_verified',
  },
} as unknown as AppConfig

const READY_WORKER: GpuWorkerStatus = {
  role: 'image',
  label: 'Local image worker (FLUX.2 Klein 4B)',
  configured: true,
  dedicated: false,
  state: 'ready',
  message: 'Exact package, execution canary, and benchmark evidence passed.',
  startup_ready: true,
  execution_proven: true,
  benchmark_state: 'passed',
  blocker_code: '',
}

afterEach(cleanup)

describe('ImageSection supported backend selection', () => {
  it('keeps local FLUX.2 disabled until live readiness passes', () => {
    const update = vi.fn()
    render(
      <ImageSection
        s={{}}
        config={CANDIDATE_CONFIG}
        imageWorker={null}
        update={update}
      />,
    )

    expect(screen.getByRole('radio', { name: /Nano Banana/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Local FLUX\.2 Klein 4B/ })).toBeDisabled()
    expect(screen.getByText(/Candidate artifacts are not installed/i)).toBeInTheDocument()
    expect(screen.getByText(/benchmark=not_run/)).toBeInTheDocument()
    expect(update).not.toHaveBeenCalled()
  })

  it('selects the local backend only from an exact Ready projection', () => {
    const update = vi.fn()
    render(
      <ImageSection
        s={{ identity_backend: 'gemini_multiref' }}
        config={CANDIDATE_CONFIG}
        imageWorker={READY_WORKER}
        update={update}
      />,
    )

    const local = screen.getByRole('radio', { name: /Local FLUX\.2 Klein 4B/ })
    expect(local).toBeEnabled()
    fireEvent.click(local)
    expect(update).toHaveBeenCalledWith('identity_backend', 'local_flux2_klein')
  })

  it('surfaces an unsupported stored value without painting a saved choice', () => {
    render(
      <ImageSection
        s={{ identity_backend: 'retired-value' }}
        config={CANDIDATE_CONFIG}
        imageWorker={null}
        update={vi.fn()}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('unsupported image backend')
    expect(screen.getByRole('radio', { name: /Nano Banana/ })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: /Local FLUX\.2 Klein 4B/ })).not.toBeChecked()
  })

  it('has no automated accessibility violations when local is ready', async () => {
    const { container } = render(
      <ImageSection
        s={{ identity_backend: 'local_flux2_klein' }}
        config={CANDIDATE_CONFIG}
        imageWorker={READY_WORKER}
        update={vi.fn()}
      />,
    )

    await expectNoAxeViolations(container)
  })
})
