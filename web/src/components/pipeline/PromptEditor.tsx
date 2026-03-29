import { useState } from 'react'

interface Props {
  shotId: string
  projectId: string
  currentPrompt: string
  onClose: () => void
  onSaved: () => void
}

// Parse [SHOT][SCENE][ACTION][OUTFIT][QUALITY] sections
function parseStructured(prompt: string): Record<string, string> {
  const sections: Record<string, string> = {}
  for (const tag of ['SHOT', 'SCENE', 'ACTION', 'OUTFIT', 'QUALITY']) {
    const match = prompt.match(new RegExp(`\\[${tag}\\]\\s*(.+?)(?=\\[(?:SHOT|SCENE|ACTION|OUTFIT|QUALITY)\\]|$)`, 's'))
    if (match) sections[tag] = match[1].trim()
  }
  // If no sections found, put everything in SCENE
  if (Object.keys(sections).length === 0) {
    sections['SCENE'] = prompt
  }
  return sections
}

function assembleSections(sections: Record<string, string>): string {
  return Object.entries(sections)
    .filter(([, v]) => v.trim())
    .map(([k, v]) => `[${k}] ${v}`)
    .join(' ')
}

const SECTION_LABELS: Record<string, { label: string; color: string; placeholder: string }> = {
  SHOT: { label: 'Camera', color: 'text-cyan-400', placeholder: 'e.g. Medium shot, 85mm f/1.4 lens, shallow DoF' },
  SCENE: { label: 'Scene', color: 'text-indigo-400', placeholder: 'e.g. Snowy park with bare trees, overcast sky, 4500K' },
  ACTION: { label: 'Action', color: 'text-amber-400', placeholder: 'e.g. Walking toward camera, looking directly at camera' },
  OUTFIT: { label: 'Outfit', color: 'text-pink-400', placeholder: 'e.g. Red wool coat over white turtleneck' },
  QUALITY: { label: 'Quality', color: 'text-gray-400', placeholder: 'e.g. Shot on Arri Alexa, 4K RAW, photorealistic' },
}

export default function PromptEditor({ shotId, projectId, currentPrompt, onClose, onSaved }: Props) {
  const [sections, setSections] = useState(() => parseStructured(currentPrompt))
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    const newPrompt = assembleSections(sections)
    await fetch(`/api/projects/${projectId}/shots/${shotId}/prompt`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: newPrompt }),
    })
    setSaving(false)
    onSaved()
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-cinema-panel border border-cinema-border rounded-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-cinema-border">
          <h3 className="text-sm font-semibold text-cinema-text">Edit Shot Prompt</h3>
          <button onClick={onClose} className="text-cinema-muted hover:text-cinema-text text-lg">&times;</button>
        </div>

        <div className="p-5 space-y-4">
          {Object.entries(SECTION_LABELS).map(([tag, cfg]) => (
            <div key={tag}>
              <label className={`text-xs font-mono font-bold ${cfg.color} mb-1 block`}>
                [{tag}] {cfg.label}
              </label>
              <textarea
                value={sections[tag] || ''}
                onChange={e => setSections(s => ({ ...s, [tag]: e.target.value }))}
                placeholder={cfg.placeholder}
                rows={tag === 'SCENE' ? 3 : 2}
                className="w-full bg-cinema-bg border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text
                  focus:border-cinema-accent focus:outline-none resize-none"
              />
            </div>
          ))}

          <div className="bg-cinema-bg border border-cinema-border rounded p-3">
            <p className="text-[10px] text-cinema-muted mb-1 font-mono">ASSEMBLED PROMPT:</p>
            <p className="text-xs text-cinema-text/70">{assembleSections(sections)}</p>
          </div>
        </div>

        <div className="flex justify-end gap-3 px-5 py-3 border-t border-cinema-border">
          <button
            onClick={onClose}
            className="text-sm px-4 py-2 rounded text-cinema-muted hover:text-cinema-text"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="text-sm px-5 py-2 rounded bg-cinema-accent hover:bg-cinema-accent2 text-white font-medium
              disabled:opacity-40"
          >
            {saving ? 'Saving...' : 'Save & Regenerate'}
          </button>
        </div>
      </div>
    </div>
  )
}
