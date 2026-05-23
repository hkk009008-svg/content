import type { Project, AppConfig } from '../types/project'
import {
  ProductionSection,
  MaxQualityTierSection,
  CostEstimatorSection,
  BudgetSection,
  AudioSection,
  AudioSyncSection,
  PostProcessingSection,
  QualitySection,
  ApiEnginesSection,
  AdvancedSection,
} from './settings'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

export default function SettingsPanel({ project, config, onRefresh }: Props) {
  const s = project.global_settings as any

  const update = async (key: string, value: any) => {
    const res = await fetch(`${API}/projects/${project.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_settings: { ...s, [key]: value } }),
    })
    if (res.ok) onRefresh()
  }

  return (
    <div className="p-4">
      <ProductionSection s={s} config={config} project={project} update={update} onRefresh={onRefresh} />
      <MaxQualityTierSection s={s} project={project} update={update} />
      <CostEstimatorSection s={s} />
      <BudgetSection s={s} update={update} />
      <AudioSection s={s} update={update} />
      <AudioSyncSection s={s} config={config} update={update} />
      <PostProcessingSection s={s} update={update} />
      <QualitySection s={s} update={update} />
      <ApiEnginesSection s={s} config={config} update={update} />
      <AdvancedSection s={s} config={config} project={project} />
    </div>
  )
}
