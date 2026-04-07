import { definePreview } from '@storybook/react-vite'
import { sb } from 'storybook/test'
import '../src/index.css'

sb.mock(import('../src/lib/api.ts'), { spy: true })
sb.mock(import('../src/components/writing/useSelectionLookup.ts'), { spy: true })

export default definePreview({
  tags: ['autodocs'],
  parameters: {
    controls: {
      expanded: true,
    },
    layout: 'padded',
    options: {
      storySort: {
        order: ['Pages', ['Workbench', 'Visualization', 'Management', '*'], 'Navigation', 'Graph', 'Workflow', 'Writing'],
      },
    },
  },
})
