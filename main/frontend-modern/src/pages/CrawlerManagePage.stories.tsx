import type { Meta, StoryObj } from '@storybook/react-vite'
import CrawlerManagePage from './CrawlerManagePage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/CrawlerManagePage',
  component: CrawlerManagePage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof CrawlerManagePage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: '',
  },
}
