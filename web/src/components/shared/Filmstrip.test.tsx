import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import Filmstrip from './Filmstrip'
import type { Project, Shot, ShotState } from '../../types/project'

function makeShot(i: number): Shot {
  return {
    id: `shot-${i}`,
    prompt: `Shot ${i} prompt`,
    camera: '',
    visual_effect: '',
    target_api: 'veo_3',
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

function makeProject(shotCount: number): Project {
  return {
    id: 'proj1',
    name: 'Test Reel',
    characters: [],
    locations: [],
    objects: [],
    scenes: [
      {
        id: 'scene1',
        order: 0,
        title: 'Opening',
        location_id: '',
        characters_present: [],
        action: '',
        dialogue: '',
        mood: '',
        camera_direction: '',
        duration_seconds: 5,
        num_shots: shotCount,
        shots: Array.from({ length: shotCount }, (_, i) => makeShot(i)),
      },
    ],
    global_settings: {
      aspect_ratio: '9:16',
      music_mood: '',
      color_palette: '',
      style_rules: {},
    },
  }
}

describe('Filmstrip', () => {
  it('windows to 40 shots and shows a "+N more" control for the overflow', () => {
    const { container } = render(<Filmstrip project={makeProject(45)} projectId="proj1" />)

    const tiles = container.querySelectorAll('[data-shot-id]')
    expect(tiles).toHaveLength(40)
    expect(screen.getByText('+5 more')).toBeInTheDocument()
  })

  it('clicking the "+N more" control reveals the remaining shots', () => {
    const { container } = render(<Filmstrip project={makeProject(45)} projectId="proj1" />)

    fireEvent.click(screen.getByText('+5 more'))

    expect(container.querySelectorAll('[data-shot-id]')).toHaveLength(45)
  })

  it('uses the live ShotState status (done) when one exists for a shot', () => {
    const shotStates = new Map<string, Partial<ShotState>>([
      ['shot-0', { id: 'shot-0', scene_id: 'scene1', status: 'complete' }],
    ])
    const { container } = render(
      <Filmstrip project={makeProject(3)} shotStates={shotStates} projectId="proj1" />,
    )

    const tile = container.querySelector('[data-shot-id="shot-0"]')
    expect(tile).not.toBeNull()
    expect(tile).toHaveClass('status-done')
    expect(tile).toHaveAttribute('data-status', 'done')
  })

  it('falls back to plan_status when no ShotState exists for a shot', () => {
    const project = makeProject(2)
    project.scenes[0].shots[0].plan_status = 'approved'
    project.scenes[0].shots[1].plan_status = 'rejected'
    const { container } = render(<Filmstrip project={project} projectId="proj1" />)

    expect(container.querySelector('[data-shot-id="shot-0"]')).toHaveClass('status-done')
    expect(container.querySelector('[data-shot-id="shot-1"]')).toHaveClass('status-failed')
  })

  it('fires onShotClick with the shot id when a tile is clicked', () => {
    const onShotClick = vi.fn()
    const { container } = render(
      <Filmstrip project={makeProject(3)} projectId="proj1" onShotClick={onShotClick} />,
    )

    fireEvent.click(container.querySelector('[data-shot-id="shot-1"]')!)

    expect(onShotClick).toHaveBeenCalledWith('shot-1')
  })
})
