import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AutoApproveAuditEntry, Project } from '../../types/project'
import PostRunSummary from './PostRunSummary'
import { expectNoAxeViolations } from '../../test/a11y-setup'

function audit(
  gate: AutoApproveAuditEntry['gate'],
  outcome: 'approved' | 'vetoed' | 'deferred',
  timestamp: string,
): AutoApproveAuditEntry {
  return {
    gate,
    auto_approved: outcome === 'approved',
    deferred: outcome === 'deferred',
    vetoes: outcome === 'approved' ? [] : ['Manual review required'],
    rule_names: outcome === 'deferred' ? ['evaluation_error'] : ['quality_rule'],
    timestamp,
  }
}

function projectWithAudit(): Project {
  return {
    id: 'p1',
    name: 'Audit summary',
    characters: [],
    locations: [],
    objects: [],
    global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
    scenes: [{
      id: 'scene-1',
      order: 0,
      title: 'Scene',
      location_id: '',
      characters_present: [],
      action: '',
      dialogue: '',
      mood: '',
      camera_direction: '',
      duration_seconds: 4,
      num_shots: 3,
      shots: [
        { id: 'approved-shot', auto_approve_audit: [audit('plan', 'approved', '2026-08-04T00:00:00Z')] },
        { id: 'vetoed-shot', auto_approve_audit: [audit('image', 'vetoed', '2026-08-04T00:00:01Z')] },
        { id: 'deferred-shot', auto_approve_audit: [audit('final', 'deferred', '2026-08-04T00:00:02Z')] },
      ],
    }],
  } as unknown as Project
}

describe('PostRunSummary audit outcomes', () => {
  afterEach(cleanup)

  it('counts and renders deferred evaluation separately from a substantive veto', () => {
    render(
      <PostRunSummary
        project={projectWithAudit()}
        isOpen={true}
        onClose={vi.fn()}
      />,
    )

    expect(
      screen.getByText(/1 decision auto-approved, 1 vetoed, 1 deferred for manual review in the latest recorded state for each shot and gate/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Project auto-approve history' })).toBeInTheDocument()
    expect(screen.queryByText(/across this run/i)).toBeNull()

    const imageCard = screen.getByText('Image').parentElement
    const finalCard = screen.getByText('Final').parentElement
    expect(imageCard).not.toBeNull()
    expect(finalCard).not.toBeNull()
    expect(within(imageCard!).getByText('vetoed')).toBeInTheDocument()
    expect(within(imageCard!).queryByText('deferred')).toBeNull()
    expect(within(finalCard!).getByText('deferred')).toBeInTheDocument()
    expect(within(finalCard!).queryByText('vetoed')).toBeNull()
  })

  it('moves focus into the shared dialog and closes it with Escape', async () => {
    const onClose = vi.fn()
    render(
      <PostRunSummary project={projectWithAudit()} isOpen={true} onClose={onClose} />,
    )

    await waitFor(() => expect(screen.getByRole('button', { name: 'Close summary' })).toHaveFocus())
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('opens the reject form as the sole modal, labels and focuses its required reason field, then restores the history dialog', async () => {
    render(
      <PostRunSummary project={projectWithAudit()} isOpen={true} onClose={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
    expect(screen.queryByRole('dialog', { name: 'Project auto-approve history' })).toBeNull()

    const rejectDialog = screen.getByRole('dialog', {
      name: 'Reject auto-approve decision for Plan gate',
    })
    expect(rejectDialog).toBeInTheDocument()
    const reason = screen.getByRole('textbox', { name: /Reason/i })
    expect(reason).toBeRequired()
    await waitFor(() => expect(reason).toHaveFocus())

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Project auto-approve history' })).toBeInTheDocument()
    })
  })

  it('has no automated accessibility violations in either dialog state', async () => {
    render(
      <PostRunSummary project={projectWithAudit()} isOpen={true} onClose={vi.fn()} />,
    )
    await expectNoAxeViolations(document.body)

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
    await expectNoAxeViolations(document.body)
  })
})
