import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { expectNoAxeViolations } from '../../test/a11y-setup'
import {
  Badge,
  BusyState,
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  LiveRegion,
  LoadingState,
  Meter,
  OfflineState,
  Section,
  SelectPill,
  StatusDot,
  SuccessState,
  Toggle,
} from './index'
import MediaAsset from './MediaAsset'

/**
 * Automated accessibility harness (slice 13a). Runs jest-axe's `axe()`
 * against every shared primitive in its representative states -- catches
 * missing accessible names, invalid ARIA usage, and structural issues that
 * a purely behavioral render/click test wouldn't notice.
 *
 * Run via `npm --prefix web run test:a11y` (filters to files whose path
 * contains "a11y", i.e. this file); writes its output to
 * `logs/ui/product-unification/a11y.txt` via that script.
 */

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('shared primitive accessibility (jest-axe)', () => {
  it('LoadingState has no violations', async () => {
    const { container } = render(<LoadingState label="Loading" />)
    await expectNoAxeViolations(container)
  })

  it('EmptyState (with action) has no violations', async () => {
    const { container } = render(
      <EmptyState message="No scenes yet" hint="Add one to begin" action={{ label: 'Add scene', onClick: () => {} }} />,
    )
    await expectNoAxeViolations(container)
  })

  it('ErrorState (with retry/dismiss) has no violations', async () => {
    const { container } = render(
      <ErrorState message="The render failed." hint="Check the log" onRetry={() => {}} onDismiss={() => {}} />,
    )
    await expectNoAxeViolations(container)
  })

  it('OfflineState (with retry) has no violations', async () => {
    const { container } = render(<OfflineState onRetry={() => {}} />)
    await expectNoAxeViolations(container)
  })

  it('BusyState has no violations', async () => {
    const { container } = render(<BusyState label="Regenerating shot" />)
    await expectNoAxeViolations(container)
  })

  it('SuccessState (with dismiss) has no violations', async () => {
    const { container } = render(<SuccessState message="Saved." onDismiss={() => {}} />)
    await expectNoAxeViolations(container)
  })

  it('LiveRegion (polite and assertive) has no violations', async () => {
    const { container } = render(
      <div>
        <LiveRegion message="3 of 5 shots regenerated" />
        <LiveRegion message="Budget halted the run" politeness="assertive" />
      </div>,
    )
    await expectNoAxeViolations(container)
  })

  it('Badge has no violations', async () => {
    const { container } = render(
      <div>
        <Badge variant="ok">OK</Badge>
        <Badge variant="pod">Pod</Badge>
        <Badge variant="fail">Fail</Badge>
      </div>,
    )
    await expectNoAxeViolations(container)
  })

  it('Button (primary, loading, and disabled variants) has no violations', async () => {
    const { container } = render(
      <div>
        <Button variant="brass">Go</Button>
        <Button variant="curtain" isLoading>
          Busy
        </Button>
        <Button variant="ivory-ghost" disabled>
          Disabled
        </Button>
      </div>,
    )
    await expectNoAxeViolations(container)
  })

  it('Toggle (on and off) has no violations', async () => {
    const { container } = render(
      <div>
        <Toggle checked onChange={() => {}} aria-label="Enable feature A" />
        <Toggle checked={false} onChange={() => {}} aria-label="Enable feature B" />
      </div>,
    )
    await expectNoAxeViolations(container)
  })

  it('SelectPill has no violations', async () => {
    const { container } = render(
      <SelectPill value="a" onChange={() => {}} options={['a', 'b', 'c']} aria-label="Pick one" />,
    )
    await expectNoAxeViolations(container)
  })

  it('Section (expanded) has no violations', async () => {
    const { container } = render(
      <Section title="Video">
        <p>Body content</p>
      </Section>,
    )
    await expectNoAxeViolations(container)
  })

  it('Meter has no violations', async () => {
    const { container } = render(<Meter value={3} max={10} label="Budget" right="$30 / $100" />)
    await expectNoAxeViolations(container)
  })

  it('StatusDot alongside a text label has no violations', async () => {
    const { container } = render(
      <span>
        <StatusDot status="ok" /> Ready
      </span>,
    )
    await expectNoAxeViolations(container)
  })

  it('Dialog (open, titled, with interactive content) has no violations', async () => {
    render(
      <Dialog isOpen onClose={() => {}} title="Confirm action">
        <p>Are you sure you want to proceed?</p>
        <Button variant="brass">Yes</Button>
        <Button variant="ivory-ghost">Cancel</Button>
      </Dialog>,
    )
    // Dialog renders through a portal to document.body, outside RTL's own
    // container div -- scan the whole body to actually reach it.
    await expectNoAxeViolations(document.body)
  })

  describe('MediaAsset', () => {
    beforeEach(() => {
      vi.stubGlobal('fetch', vi.fn())
    })

    it('idle state has no violations', async () => {
      const { container } = render(<MediaAsset kind="image" url={null} emptyLabel="No take yet" />)
      await expectNoAxeViolations(container)
    })
  })
})
