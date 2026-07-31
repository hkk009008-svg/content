import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { VoiceSection } from './VoiceSection'

/**
 * The lipsync cascade is the one control here that survived a file deletion:
 * `LipsyncPriorityList` used to live in `settings/AudioSyncSection.tsx`, whose
 * section component was dead while this named export stayed mounted. These
 * assertions pin the wiring — that the list renders inside Voice, and that it
 * reads/writes the server-validated `lipsync_engine_priority` key.
 */
describe('VoiceSection lipsync cascade', () => {
  const DEFAULT_CASCADE = ['SYNC_SO_V3', 'MUSETALK', 'LATENTSYNC', 'OMNIHUMAN_V1_5', 'SYNC_V2']

  it('renders the default cascade in order when the setting is unset', () => {
    render(<VoiceSection s={{}} config={null} update={vi.fn()} />)

    expect(screen.getByText('Lipsync engine priority')).toBeInTheDocument()
    for (const key of DEFAULT_CASCADE) {
      expect(screen.getByText(key)).toBeInTheDocument()
    }
  })

  it('reads an explicit priority from settings rather than the default', () => {
    render(
      <VoiceSection
        s={{ lipsync_engine_priority: ['MUSETALK', 'SYNC_V2'] }}
        config={null}
        update={vi.fn()}
      />,
    )

    expect(screen.getByText('MUSETALK')).toBeInTheDocument()
    expect(screen.getByText('SYNC_V2')).toBeInTheDocument()
    expect(screen.queryByText('SYNC_SO_V3')).toBeNull()
  })

  it('writes the reordered list back to lipsync_engine_priority', async () => {
    const update = vi.fn()
    render(<VoiceSection s={{}} config={null} update={update} />)

    await userEvent.click(screen.getByRole('button', { name: 'Move SYNC_SO_V3 down' }))

    expect(update).toHaveBeenCalledWith('lipsync_engine_priority', [
      'MUSETALK',
      'SYNC_SO_V3',
      'LATENTSYNC',
      'OMNIHUMAN_V1_5',
      'SYNC_V2',
    ])
  })

  it('disables reordering past either end of the cascade', () => {
    render(<VoiceSection s={{}} config={null} update={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Move SYNC_SO_V3 up' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move SYNC_V2 down' })).toBeDisabled()
  })
})
