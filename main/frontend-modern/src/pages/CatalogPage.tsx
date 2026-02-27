import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CopyPlus, Trash2 } from 'lucide-react'
import { createProduct, createTopic, deleteProduct, deleteTopic, listProducts, listTopics } from '../lib/api'

type CatalogPageProps = {
  projectKey: string
  variant?: 'catalog' | 'company' | 'product' | 'operation'
}

function splitTerms(raw: string) {
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

export default function CatalogPage({ projectKey, variant = 'catalog' }: CatalogPageProps) {
  const queryClient = useQueryClient()
  const [topicName, setTopicName] = useState('')
  const [topicKeywords, setTopicKeywords] = useState('')
  const [productName, setProductName] = useState('')
  const [productCategory, setProductCategory] = useState('')

  const topics = useQuery({ queryKey: ['topics', projectKey], queryFn: listTopics, enabled: Boolean(projectKey) })
  const products = useQuery({ queryKey: ['products', projectKey], queryFn: listProducts, enabled: Boolean(projectKey) })

  const createTopicMutation = useMutation({
    mutationFn: () => createTopic({ topic_name: topicName.trim(), domains: [], languages: ['zh', 'en'], keywords_seed: splitTerms(topicKeywords), subreddits: [], enabled: true }),
    onSuccess: async () => {
      setTopicName('')
      setTopicKeywords('')
      await queryClient.invalidateQueries({ queryKey: ['topics', projectKey] })
    },
  })

  const deleteTopicMutation = useMutation({
    mutationFn: (id: number) => deleteTopic(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['topics', projectKey] }),
  })

  const createProductMutation = useMutation({
    mutationFn: () => createProduct({ name: productName.trim(), category: productCategory.trim() || null, enabled: true }),
    onSuccess: async () => {
      setProductName('')
      setProductCategory('')
      await queryClient.invalidateQueries({ queryKey: ['products', projectKey] })
    },
  })

  const deleteProductMutation = useMutation({
    mutationFn: (id: number) => deleteProduct(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products', projectKey] }),
  })

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'catalog' ? '行业公司/商品/经营' : `对象视图: ${variant}`}</h2>
        </div>
      </section>
      <section className="panel two-col">
        <div>
          <div className="panel-header"><h2>主题管理</h2></div>
          <div className="form-grid cols-2">
            <label><span>topic_name</span><input value={topicName} onChange={(e) => setTopicName(e.target.value)} /></label>
            <label><span>keywords(,)</span><input value={topicKeywords} onChange={(e) => setTopicKeywords(e.target.value)} /></label>
          </div>
          <div className="inline-actions">
            <button disabled={createTopicMutation.isPending || !topicName.trim()} onClick={() => createTopicMutation.mutate()}><CopyPlus size={14} />新增主题</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>name</th><th>enabled</th><th>keywords</th><th>action</th></tr></thead>
              <tbody>
                {(topics.data || []).map((row) => (
                  <tr key={row.id}>
                    <td>{row.topic_name}</td>
                    <td>{String(row.enabled)}</td>
                    <td>{(row.keywords_seed || []).join(', ') || '-'}</td>
                    <td><button disabled={deleteTopicMutation.isPending} onClick={() => deleteTopicMutation.mutate(row.id)}><Trash2 size={12} />删除</button></td>
                  </tr>
                ))}
                {!topics.data?.length && <tr><td colSpan={4} className="empty-cell">暂无主题</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="panel-header"><h2>商品管理</h2></div>
          <div className="form-grid cols-2">
            <label><span>name</span><input value={productName} onChange={(e) => setProductName(e.target.value)} /></label>
            <label><span>category</span><input value={productCategory} onChange={(e) => setProductCategory(e.target.value)} /></label>
          </div>
          <div className="inline-actions">
            <button disabled={createProductMutation.isPending || !productName.trim()} onClick={() => createProductMutation.mutate()}><CopyPlus size={14} />新增商品</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>name</th><th>category</th><th>enabled</th><th>action</th></tr></thead>
              <tbody>
                {(products.data || []).map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>{row.category || '-'}</td>
                    <td>{String(row.enabled)}</td>
                    <td><button disabled={deleteProductMutation.isPending} onClick={() => deleteProductMutation.mutate(row.id)}><Trash2 size={12} />删除</button></td>
                  </tr>
                ))}
                {!products.data?.length && <tr><td colSpan={4} className="empty-cell">暂无商品</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}
