import type { Meta, StoryObj } from '@storybook/react-vite'
import MarkdownPreview from './MarkdownPreview'

const meta = {
  title: 'Writing/MarkdownPreview',
  component: MarkdownPreview,
  args: {
    markdown: '# 市场快照',
  },
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 720 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof MarkdownPreview>

export default meta

type Story = StoryObj<typeof meta>

export const RichContent: Story = {
  args: {
    markdown: [
      '# 市场快照',
      '',
      '## 核心结论',
      '- 新能源相关政策热度上升',
      '- 上游原材料价格波动仍然明显',
      '',
      '> 本周应重点跟踪锂盐与储能链条。',
      '',
      '参考链接：[国家能源局](https://www.nea.gov.cn/)',
      '',
      '```ts',
      "const status = 'watch';",
      '```',
    ].join('\n'),
  },
}

export const Empty: Story = {
  args: {
    markdown: '',
  },
}
