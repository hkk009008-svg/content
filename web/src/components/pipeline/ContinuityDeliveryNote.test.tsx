import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ContinuityDeliveryNote from './ContinuityDeliveryNote'

describe('ContinuityDeliveryNote', () => {
  it('names the drop when there was an anchor and it did not go', () => {
    // The whole reason the note exists: the anchor is dropped WITHOUT failing
    // the call — a crowded multi-character shot spends its budget on faces, an
    // upload can fail, the text-to-image routes take no references at all. A
    // drifting scene is then indistinguishable from one never told about the
    // previous shot, which is the difference between "regenerate" and "this
    // shot was never given the information".
    const { container } = render(
      <ContinuityDeliveryNote continuityReference="takes/prev.png" delivered={false} />,
    )
    expect(container.textContent).toContain('was not sent with this one')
    // And it does not blame the generator for the mismatch.
    expect(container.textContent).toContain('not a generation fault')
  })

  it('is silent when the anchor was delivered', () => {
    // Success is the expected state. A banner on every correct shot is noise,
    // and noise is what makes the one meaningful banner invisible.
    const { container } = render(
      <ContinuityDeliveryNote continuityReference="takes/prev.png" delivered />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('is silent on a shot that had no predecessor', () => {
    // Every scene's FIRST shot has no approved anchor. Reporting its absence
    // would fire on a large share of all shots and mean nothing.
    const { container } = render(
      <ContinuityDeliveryNote continuityReference="" delivered={false} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('is silent when the take predates the field entirely', () => {
    // Takes generated before continuity was recorded carry neither key.
    // Undefined must read as "nothing to say", not as "the anchor was dropped".
    const { container } = render(<ContinuityDeliveryNote />)
    expect(container.firstChild).toBeNull()
  })
})
