import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import Timeline from './Timeline'
import type { Project, Shot } from '../../types/project'

function makeShot(id: string): Shot {
  return {
    id,
    prompt: '',
    camera: '',
    visual_effect: '',
    target_api: 'AUTO',
    scene_foley: '',
    characters_in_frame: [],
    primary_character: '',
    objects_in_frame: [],
    primary_object: '',
    action_context: '',
    generated_image: '',
    generated_video: '',
    plan_status: 'pending_review',
    keyframe_takes: [],
    approved_keyframe_take_id: '',
    motion_takes: [],
    approved_motion_take_id: '',
    postprocess_variants: [],
    approved_final_take_id: '',
    diagnostics: [],
    intent_notes: '',
    negative_constraints: '',
    continuity_constraints: '',
  }
}

const project: Project = {
  id: 'proj1',
  name: 'Test Reel',
  characters: [],
  locations: [],
  objects: [],
  global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
  scenes: [
    {
      id: 'sceneA',
      order: 1,
      title: 'Scene A',
      location_id: '',
      characters_present: [],
      action: '',
      dialogue: '',
      mood: '',
      camera_direction: '',
      duration_seconds: 8,
      num_shots: 2,
      shots: [makeShot('a1'), makeShot('a2')],
    },
    {
      id: 'sceneB',
      order: 2,
      title: 'Scene B',
      location_id: '',
      characters_present: [],
      action: '',
      dialogue: '',
      mood: '',
      camera_direction: '',
      duration_seconds: 8,
      num_shots: 2,
      shots: [makeShot('b1'), makeShot('b2')],
    },
  ],
}

describe('Timeline', () => {
  it('renders 4 clips grouped by scene', () => {
    render(<Timeline project={project} shotStates={new Map()} activeShotId={null} onSelect={vi.fn()} />)

    expect(screen.getByText('Scene A')).toBeInTheDocument()
    expect(screen.getByText('Scene B')).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(4)
  })

  it('clicking clip 3 calls onSelect with that shot id', () => {
    const onSelect = vi.fn()
    render(<Timeline project={project} shotStates={new Map()} activeShotId={null} onSelect={onSelect} />)

    const clips = screen.getAllByRole('button')
    fireEvent.click(clips[2]) // 3rd clip overall = scene B's first shot

    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith('b1')
  })

  it('highlights the active clip with border-acc', () => {
    render(<Timeline project={project} shotStates={new Map()} activeShotId="a2" onSelect={vi.fn()} />)

    const activeClip = document.querySelector('[data-shot-id="a2"]')
    const inactiveClip = document.querySelector('[data-shot-id="a1"]')
    expect(activeClip?.className).toContain('border-acc')
    expect(inactiveClip?.className).not.toContain('border-acc')
  })
})
