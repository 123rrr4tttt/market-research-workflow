import { Suspense, type ReactNode } from 'react'
import { translate, type AppLocale } from '../platform/i18n'
import { moduleRendererBindings } from './moduleContributionRule'
import { type KernelModuleKey, type KernelRenderShellMode } from './types'

type RenderKernelModuleContentArgs = {
  moduleKey: KernelModuleKey
  projectKey: string
  onProjectChange: (nextProjectKey: string) => void
  locale: AppLocale
  shellMode?: KernelRenderShellMode
}

function renderModuleNode(args: RenderKernelModuleContentArgs): ReactNode {
  const { renderer } = moduleRendererBindings[args.moduleKey]
  return renderer(args)
}

export function renderKernelModuleContent(args: RenderKernelModuleContentArgs): ReactNode {
  return (
    <Suspense fallback={<div className="kernel-loading">{translate(args.locale, 'shared.loading')}</div>}>
      {renderModuleNode(args)}
    </Suspense>
  )
}
