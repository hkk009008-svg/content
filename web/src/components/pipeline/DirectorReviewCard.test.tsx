import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import DirectorReviewCard from './DirectorReviewCard'

describe('DirectorReviewCard', () => {
  afterEach(cleanup)

  it('renders REVIEW_REQUIRED as an alert that explicitly requires manual review', () => {
    render(<DirectorReviewCard review={{ decision: 'REVIEW_REQUIRED' }} />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveAttribute('data-review-state', 'manual-required')
    expect(screen.getByText('Chief Director: REVIEW_REQUIRED')).toBeInTheDocument()
    expect(screen.getByText(/manual review is required/i)).toBeInTheDocument()
  })

  it('fails an unrecognized decision closed instead of inheriting APPROVED styling', () => {
    render(<DirectorReviewCard review={{ decision: 'PARTIAL_APPROVAL' }} />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveAttribute('data-review-state', 'manual-required')
    expect(screen.getByText('Chief Director: UNRECOGNIZED (PARTIAL_APPROVAL)')).toHaveClass('text-warn')
    expect(screen.getByText(/treated as review required/i)).toBeInTheDocument()
    expect(screen.queryByText('Chief Director: APPROVED')).toBeNull()
  })

  it('tolerates absent optional fields while preserving a real approval', () => {
    render(<DirectorReviewCard review={{ decision: 'APPROVED' }} />)

    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('data-review-state', 'approved')
    expect(screen.getByText('Chief Director: APPROVED')).toBeInTheDocument()
    expect(screen.queryByText(/manual review/i)).toBeNull()
  })

  it('renders finite quality and safe violation text when supplied', () => {
    render(
      <DirectorReviewCard
        review={{
          decision: 'REJECTED',
          quality_score: 0.42,
          reasoning: 'Continuity mismatch.',
          violations: ['Wardrobe changed'],
        }}
      />,
    )

    expect(screen.getByText('Quality: 42%')).toBeInTheDocument()
    expect(screen.getByText('Continuity mismatch.')).toBeInTheDocument()
    expect(screen.getByText(/Wardrobe changed/)).toBeInTheDocument()
  })
})
