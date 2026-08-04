import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { expectNoAxeViolations } from '../../../test/a11y-setup'
import { AutoApproveSection } from './AutoApproveSection'

describe('AutoApproveSection', () => {
  it('has no automated accessibility violations', async () => {
    const { container } = render(<AutoApproveSection s={{}} update={vi.fn()} />)
    await expectNoAxeViolations(container)
  })

  it('shows conservative runtime defaults and the UNKNOWN review rule', () => {
    render(<AutoApproveSection s={{}} update={vi.fn()} />)

    expect(screen.getByRole('switch', { name: 'Auto-approve eligible gates' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('slider', { name: 'Final lip-sync threshold' })).toHaveValue('0.8')
    expect(screen.getByRole('switch', { name: 'Require human after upstream auto-approval' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText(/UNKNOWN or unavailable lip-sync evidence always vetoes/i)).toHaveTextContent(
      'even when the numeric threshold is 0',
    )
  })

  it('updates one nested value while preserving the other auto-approve settings', async () => {
    const current = {
      enabled: true,
      final_min_lipsync: 0.75,
      final_require_human_if_upstream_auto: true,
      image_min_composite: 0.6,
    }
    let queued = current
    const update = vi.fn((_key: string, value: unknown) => {
      queued = typeof value === 'function'
        ? (value as (prior: typeof current) => typeof current)(queued)
        : value as typeof current
    })
    render(<AutoApproveSection s={{ auto_approve: current }} update={update} />)

    await userEvent.click(screen.getByRole('switch', { name: 'Auto-approve eligible gates' }))
    expect(update).toHaveBeenLastCalledWith('auto_approve', expect.any(Function))
    expect(queued).toEqual({ ...current, enabled: false })

    fireEvent.change(screen.getByRole('slider', { name: 'Final lip-sync threshold' }), {
      target: { value: '0.9' },
    })
    expect(queued).toEqual({
      ...current,
      enabled: false,
      final_min_lipsync: 0.9,
    })

    await userEvent.click(screen.getByRole('switch', { name: 'Require human after upstream auto-approval' }))
    expect(queued).toEqual({
      ...current,
      enabled: false,
      final_min_lipsync: 0.9,
      final_require_human_if_upstream_auto: false,
    })
  })
})
