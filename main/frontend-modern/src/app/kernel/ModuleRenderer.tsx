import type { KernelModuleKey } from './types'
import { renderKernelModuleContent, type KernelRenderShellMode } from './renderKernelModuleContent'

type Props = {
  moduleKey: KernelModuleKey
  projectKey: string
  onProjectChange: (nextProjectKey: string) => void
  shellMode?: KernelRenderShellMode
}

export default function ModuleRenderer({ moduleKey, projectKey, onProjectChange, shellMode = 'default' }: Props) {
  return renderKernelModuleContent({ moduleKey, projectKey, onProjectChange, shellMode })
}
