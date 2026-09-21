import { useAppLocale } from '../platform/i18n'
import type { KernelModuleKey, KernelRenderShellMode, KernelRouteRenderVariant } from './types'
import { renderKernelModuleContent } from './renderKernelModuleContent'

type Props = {
  moduleKey: KernelModuleKey
  projectKey: string
  onProjectChange: (nextProjectKey: string) => void
  shellMode?: KernelRenderShellMode
  renderVariant?: KernelRouteRenderVariant
}

export default function ModuleRenderer({ moduleKey, projectKey, onProjectChange, shellMode = 'default', renderVariant }: Props) {
  const locale = useAppLocale()

  return renderKernelModuleContent({ moduleKey, projectKey, onProjectChange, shellMode, renderVariant, locale })
}
