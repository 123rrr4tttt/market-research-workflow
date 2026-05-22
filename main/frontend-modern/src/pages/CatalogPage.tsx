import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CopyPlus, Trash2 } from 'lucide-react'
import { createProduct, createTopic, deleteProduct, deleteTopic, listProducts, listTopics } from '../lib/api'
import { translate, useAppLocale } from '../app/platform/i18n'
import { queryKeys } from '../lib/queryKeys'

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

function formatCatalogTemplate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

export default function CatalogPage({ projectKey, variant = 'catalog' }: CatalogPageProps) {
  const locale = useAppLocale()
  const queryClient = useQueryClient()
  const [topicName, setTopicName] = useState('')
  const [topicKeywords, setTopicKeywords] = useState('')
  const [productName, setProductName] = useState('')
  const [productCategory, setProductCategory] = useState('')
  type CatalogMessageKey = Parameters<typeof translate>[1]
  const t = (key: CatalogMessageKey, fallback?: string) => translate(locale, key, fallback)
  const variantLabels: Record<NonNullable<CatalogPageProps['variant']>, string> = {
    catalog: t('catalogPage.variant.catalog'),
    company: t('catalogPage.variant.company'),
    product: t('catalogPage.variant.product'),
    operation: t('catalogPage.variant.operation'),
  }
  const pageTitle =
    variant === 'catalog'
      ? t('catalogPage.title.catalog')
      : formatCatalogTemplate(t('catalogPage.title.objectView'), { variant: variantLabels[variant] || variant })
  const enabledLabel = (enabled: boolean) => t(enabled ? 'catalogPage.status.enabled' : 'catalogPage.status.disabled')

  const topics = useQuery({ queryKey: queryKeys.catalog.topics(projectKey), queryFn: listTopics, enabled: Boolean(projectKey) })
  const products = useQuery({ queryKey: queryKeys.catalog.products(projectKey), queryFn: listProducts, enabled: Boolean(projectKey) })

  const createTopicMutation = useMutation({
    mutationFn: () => createTopic({ topic_name: topicName.trim(), domains: [], languages: ['zh', 'en'], keywords_seed: splitTerms(topicKeywords), subreddits: [], enabled: true }),
    onSuccess: async () => {
      setTopicName('')
      setTopicKeywords('')
      await queryClient.invalidateQueries({ queryKey: queryKeys.catalog.topics(projectKey) })
    },
  })

  const deleteTopicMutation = useMutation({
    mutationFn: (id: number) => deleteTopic(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.catalog.topics(projectKey) }),
  })

  const createProductMutation = useMutation({
    mutationFn: () => createProduct({ name: productName.trim(), category: productCategory.trim() || null, enabled: true }),
    onSuccess: async () => {
      setProductName('')
      setProductCategory('')
      await queryClient.invalidateQueries({ queryKey: queryKeys.catalog.products(projectKey) })
    },
  })

  const deleteProductMutation = useMutation({
    mutationFn: (id: number) => deleteProduct(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.catalog.products(projectKey) }),
  })

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{pageTitle}</h2>
        </div>
      </section>
      <section className="panel two-col">
        <div>
          <div className="panel-header"><h2>{t('catalogPage.section.topics')}</h2></div>
          <div className="form-grid cols-2">
            <label><span>{t('catalogPage.field.topicName')}</span><input value={topicName} onChange={(e) => setTopicName(e.target.value)} /></label>
            <label><span>{t('catalogPage.field.keywords')}</span><input value={topicKeywords} onChange={(e) => setTopicKeywords(e.target.value)} /></label>
          </div>
          <div className="inline-actions">
            <button disabled={createTopicMutation.isPending || !topicName.trim()} onClick={() => createTopicMutation.mutate()}><CopyPlus size={14} />{t('catalogPage.action.createTopic')}</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t('catalogPage.field.name')}</th><th>{t('catalogPage.field.enabled')}</th><th>{t('catalogPage.field.keywords')}</th><th>{t('catalogPage.field.actions')}</th></tr></thead>
              <tbody>
                {(topics.data || []).map((row) => (
                  <tr key={row.id}>
                    <td>{row.topic_name}</td>
                    <td>{enabledLabel(row.enabled)}</td>
                    <td>{(row.keywords_seed || []).join(', ') || '-'}</td>
                    <td><button disabled={deleteTopicMutation.isPending} onClick={() => deleteTopicMutation.mutate(row.id)}><Trash2 size={12} />{t('catalogPage.action.delete')}</button></td>
                  </tr>
                ))}
                {!topics.data?.length && <tr><td colSpan={4} className="empty-cell">{t('catalogPage.empty.topics')}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="panel-header"><h2>{t('catalogPage.section.products')}</h2></div>
          <div className="form-grid cols-2">
            <label><span>{t('catalogPage.field.name')}</span><input value={productName} onChange={(e) => setProductName(e.target.value)} /></label>
            <label><span>{t('catalogPage.field.category')}</span><input value={productCategory} onChange={(e) => setProductCategory(e.target.value)} /></label>
          </div>
          <div className="inline-actions">
            <button disabled={createProductMutation.isPending || !productName.trim()} onClick={() => createProductMutation.mutate()}><CopyPlus size={14} />{t('catalogPage.action.createProduct')}</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t('catalogPage.field.name')}</th><th>{t('catalogPage.field.category')}</th><th>{t('catalogPage.field.enabled')}</th><th>{t('catalogPage.field.actions')}</th></tr></thead>
              <tbody>
                {(products.data || []).map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>{row.category || '-'}</td>
                    <td>{enabledLabel(row.enabled)}</td>
                    <td><button disabled={deleteProductMutation.isPending} onClick={() => deleteProductMutation.mutate(row.id)}><Trash2 size={12} />{t('catalogPage.action.delete')}</button></td>
                  </tr>
                ))}
                {!products.data?.length && <tr><td colSpan={4} className="empty-cell">{t('catalogPage.empty.products')}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}
