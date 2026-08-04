import { describe, expect, it } from 'vitest'
import type { Shot } from '../types/project'
import { shotRequiresLipsync } from './lipsyncEvidence'

function shot(overrides: Partial<Shot> = {}): Shot {
  return { id: 's1', ...overrides } as Shot
}

describe('shotRequiresLipsync', () => {
  it('recognizes legacy string and structured dialogue', () => {
    expect(shotRequiresLipsync(shot({ dialogue: 'Speak now.' }))).toBe(true)
    expect(shotRequiresLipsync(shot({ dialogue: [{ text: 'Structured line' }] }))).toBe(true)
  })

  it('recognizes backend dialogue optimizer purposes', () => {
    expect(shotRequiresLipsync(shot({
      optimizer_cache: { spec: { purpose: 'dialogue_close_up' } },
    }))).toBe(true)
    expect(shotRequiresLipsync(shot({
      optimizer_cache: { spec: { purpose: 'talking_head_full' } },
    }))).toBe(true)
  })

  it('does not make a non-dialogue shot applicable', () => {
    expect(shotRequiresLipsync(shot({ dialogue: '   ' }))).toBe(false)
    expect(shotRequiresLipsync(shot({
      optimizer_cache: { spec: { purpose: 'action_motion' } },
    }))).toBe(false)
  })
})
