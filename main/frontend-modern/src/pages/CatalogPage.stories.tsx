import type { Meta, StoryObj } from '@storybook/react-vite'
import CatalogPage from './CatalogPage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/CatalogPage',
  component: CatalogPage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof CatalogPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: '',
    variant: 'catalog',
  },
}
