import type { Decorator, Preview } from '@storybook/react-vite'
import { StorybookAppProviders } from './storybookKernelUtils'

export const pageDecorators: Decorator[] = [
  (Story) => (
    <StorybookAppProviders>
      <div style={{ minHeight: '100vh' }}>
        <Story />
      </div>
    </StorybookAppProviders>
  ),
]

export const pageParameters: Preview['parameters'] = {
  layout: 'fullscreen',
}
