import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import IdentityVerdictCard, { verdictFor } from './IdentityVerdictCard'

describe('verdictFor', () => {
  it('calls the off-angle reasons unjudged, not failed', () => {
    // ADR-092: below ~0.65 the scorer has no ordering — a real photograph of
    // the subject in profile scored 0.556 while a generated stranger scored
    // 0.570. A card that reads as a verdict there costs a re-render of correct
    // footage.
    for (const reason of [
      'no_face_detected',
      'face_angle_extreme',
      'small_face_region',
      'low_confidence_detection',
      'occlusion',
    ]) {
      expect(verdictFor(reason).standing).toBe('unjudged')
    }
  })

  it('does not present poor_lighting as a lighting measurement', () => {
    // It is the classifier's else-branch (identity/validator.py:1308) — what it
    // means is "no other test matched", and saying "poor lighting" asserts a
    // measurement nobody made.
    const verdict = verdictFor('poor_lighting')
    expect(verdict.standing).toBe('unjudged')
    expect(verdict.detail).toMatch(/else-branch/i)
    expect(verdict.headline).not.toMatch(/lighting/i)
  })

  it('is willing to call wrong_person suspect', () => {
    // The control that proves the card can say something adverse. best_sim
    // under 0.35 sits well below the band where the scorer loses its ordering.
    expect(verdictFor('wrong_person').standing).toBe('suspect')
    expect(verdictFor('video_zero_frames').standing).toBe('broken')
  })

  it('falls back to unjudged for a reason it does not recognise', () => {
    expect(verdictFor('something_new').standing).toBe('unjudged')
    expect(verdictFor(null).standing).toBe('unjudged')
  })
})

describe('IdentityVerdictCard', () => {
  it('renders nothing when the gate passed', () => {
    const { container } = render(<IdentityVerdictCard failureReason="passed" />)
    expect(container.firstChild).toBeNull()
  })

  it('states plainly that an unjudged take is not a bad take', () => {
    render(<IdentityVerdictCard failureReason="face_angle_extreme" />)
    expect(screen.getByText(/could not judge this pose/i)).toBeTruthy()
    expect(screen.getByText(/nothing here says the take is bad/i)).toBeTruthy()
  })

  it('withholds that reassurance where the gate did establish something', () => {
    // Control for the assertion above — the line must be able to be absent.
    render(<IdentityVerdictCard failureReason="wrong_person" />)
    expect(screen.queryByText(/nothing here says the take is bad/i)).toBeNull()
    expect(screen.getByText(/may not be this character/i)).toBeTruthy()
  })

  it('names the one image the gate actually compared against', () => {
    render(
      <IdentityVerdictCard
        failureReason="no_face_detected"
        comparedAgainst="characters/char_1/canonical_front.jpg"
      />,
    )
    expect(screen.getByText('canonical_front.jpg')).toBeTruthy()
    expect(screen.getByText(/a single image/i)).toBeTruthy()
  })

  it('routes to the reference sheet, which is the fixable half', async () => {
    const open = vi.fn()
    render(
      <IdentityVerdictCard failureReason="face_angle_extreme" onOpenReferenceSheet={open} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /open reference sheet/i }))
    expect(open).toHaveBeenCalledOnce()
  })

  it('prices a regenerate before the click, and lists it last', () => {
    render(
      <IdentityVerdictCard
        failureReason="face_angle_extreme"
        onOpenReferenceSheet={() => {}}
        onRegenerate={() => {}}
        regenerateCostUsd={0.05}
      />,
    )
    const buttons = screen.getAllByRole('button')
    expect(buttons[buttons.length - 1].textContent).toMatch(/regenerate/i)
    expect(screen.getByText('$0.05')).toBeTruthy()
  })

  it('offers no regenerate button when no handler is given', () => {
    render(<IdentityVerdictCard failureReason="face_angle_extreme" />)
    expect(screen.queryByRole('button', { name: /regenerate/i })).toBeNull()
  })

  it('hides the reference-sheet link when no router is available', () => {
    // The pin for a real regression: wiring this cross-link through the
    // THROWING `usePage` broke 19 unrelated ReviewStage tests at once, because
    // a convenience link became a hard dependency on <PageProvider>. ReviewStage
    // now reads `usePageOptional` and passes undefined when there is no router.
    render(<IdentityVerdictCard failureReason="face_angle_extreme" />)
    expect(screen.queryByRole('button', { name: /open reference sheet/i })).toBeNull()
    // And the verdict itself still renders — the link is the optional part.
    expect(screen.getByText(/could not judge this pose/i)).toBeTruthy()
  })
})

describe('usePageOptional', () => {
  it('returns null outside a provider instead of throwing', async () => {
    const { usePageOptional, usePage } = await import('../../context/PageContext')
    function Probe() {
      return <span>{String(usePageOptional())}</span>
    }
    render(<Probe />)
    expect(screen.getByText('null')).toBeTruthy()

    // Control: the strict hook still throws, so pages keep their loud wiring
    // check. Without this the optional variant could have been a blanket
    // loosening rather than a targeted one.
    function StrictProbe() {
      usePage()
      return null
    }
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<StrictProbe />)).toThrow(/must be used within/)
    spy.mockRestore()
  })
})
