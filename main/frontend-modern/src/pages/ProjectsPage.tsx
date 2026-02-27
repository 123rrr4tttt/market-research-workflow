import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, CopyPlus, Edit3, HardDriveDownload, RefreshCw, Trash2 } from 'lucide-react'
import { activateProject, archiveProject, createProject, deleteProject, listProjects, restoreProject, setProjectKey, updateProject } from '../lib/api'

type ProjectsPageProps = {
  projectKey: string
  onProjectChange: (key: string) => void
}

export default function ProjectsPage({ projectKey, onProjectChange }: ProjectsPageProps) {
  const queryClient = useQueryClient()
  const [newProjectKey, setNewProjectKey] = useState('')
  const [newProjectName, setNewProjectName] = useState('')
  const [editingProject, setEditingProject] = useState<{ key: string; name: string } | null>(null)

  const projects = useQuery({ queryKey: ['projects'], queryFn: listProjects })

  const actionMutation = useMutation({
    mutationFn: async (payload: { kind: 'create' | 'archive' | 'restore' | 'delete' | 'update' | 'activate'; key?: string; name?: string }) => {
      if (payload.kind === 'create') return createProject({ project_key: newProjectKey.trim(), name: newProjectName.trim(), enabled: true })
      if (!payload.key) throw new Error('缺少项目标识')
      if (payload.kind === 'archive') return archiveProject(payload.key)
      if (payload.kind === 'restore') return restoreProject(payload.key)
      if (payload.kind === 'delete') return deleteProject(payload.key, true)
      if (payload.kind === 'activate') {
        const next = setProjectKey(payload.key)
        await activateProject(next)
        onProjectChange(next)
        return { ok: true }
      }
      return updateProject(payload.key, { name: payload.name })
    },
    onSuccess: async () => {
      setNewProjectKey('')
      setNewProjectName('')
      setEditingProject(null)
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header"><h2><CopyPlus size={15} />创建项目</h2></div>
        <div className="form-grid cols-3">
          <label><span>project_key</span><input value={newProjectKey} onChange={(e) => setNewProjectKey(e.target.value)} placeholder="demo_proj_2" /></label>
          <label><span>name</span><input value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} placeholder="演示项目 2" /></label>
          <div className="inline-actions">
            <button disabled={actionMutation.isPending || !newProjectKey.trim() || !newProjectName.trim()} onClick={() => actionMutation.mutate({ kind: 'create' })}><CopyPlus size={14} />创建</button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header"><h2><HardDriveDownload size={15} />项目列表</h2><button onClick={() => queryClient.invalidateQueries({ queryKey: ['projects'] })}><RefreshCw size={14} />刷新</button></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>project_key</th><th>name</th><th>schema</th><th>enabled</th><th>active</th><th>操作</th></tr></thead>
            <tbody>
              {(projects.data || []).map((item) => (
                <tr key={item.project_key}>
                  <td>{item.project_key}</td>
                  <td>
                    {editingProject?.key === item.project_key ? (
                      <input value={editingProject.name} onChange={(e) => setEditingProject({ key: item.project_key, name: e.target.value })} />
                    ) : (
                      item.name || '-'
                    )}
                  </td>
                  <td>{item.schema_name || '-'}</td>
                  <td>{item.enabled ? 'true' : 'false'}</td>
                  <td>{item.is_active ? 'true' : 'false'}{item.project_key === projectKey ? ' (current)' : ''}</td>
                  <td>
                    <div className="inline-actions">
                      <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'activate', key: item.project_key })}>切换</button>
                      {editingProject?.key === item.project_key ? (
                        <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'update', key: item.project_key, name: editingProject.name })}><Edit3 size={12} />保存</button>
                      ) : (
                        <button onClick={() => setEditingProject({ key: item.project_key, name: item.name || '' })}><Edit3 size={12} />改名</button>
                      )}
                      {item.enabled ? (
                        <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'archive', key: item.project_key })}><Archive size={12} />归档</button>
                      ) : (
                        <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'restore', key: item.project_key })}><RefreshCw size={12} />恢复</button>
                      )}
                      <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'delete', key: item.project_key })}><Trash2 size={12} />删除</button>
                    </div>
                  </td>
                </tr>
              ))}
              {!projects.data?.length && <tr><td colSpan={6} className="empty-cell">暂无项目</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
