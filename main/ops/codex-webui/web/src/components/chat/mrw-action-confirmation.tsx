import { useEffect, useState } from 'react';
import { Check, LoaderCircle, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getApiToken } from '@/auth-token';
import { withBasePath } from '@/base-path';
import { getSocket } from '@/socket';
import { Button } from '@/components/ui/button';
import { useTimelineStore } from '@/stores/timeline-store';

type PendingAction = {
  actionId: string;
  threadId: string;
  turnId: string;
  toolName: string;
  projectKey: string;
  actionDigest?: string;
  arguments?: Record<string, unknown>;
};

function isPendingAction(value: unknown): value is PendingAction {
  if (!value || typeof value !== 'object') return false;
  const item = value as Record<string, unknown>;
  return ['actionId', 'threadId', 'turnId', 'toolName', 'projectKey']
    .every((key) => typeof item[key] === 'string' && item[key] !== '');
}

export function MrwActionConfirmation() {
  const { t } = useTranslation();
  const threadId = useTimelineStore((state) => state.threadId);
  const [actions, setActions] = useState<PendingAction[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const socket = getSocket();
    let active = true;
    const receive = (value: unknown) => {
      if (!active || !isPendingAction(value)) return;
      setActions((items) => [...items.filter((item) => item.actionId !== value.actionId), value]);
    };
    const resolved = (value: { actionId?: string }) => {
      if (active) setActions((items) => items.filter((item) => item.actionId !== value.actionId));
    };
    const refresh = async () => {
      if (!threadId) return;
      try {
        const response = await fetch(withBasePath(`/api/mrw/pending?threadId=${encodeURIComponent(threadId)}`), {
          headers: { Authorization: `Bearer ${getApiToken() ?? ''}` },
        });
        if (!response.ok) return;
        const data: unknown = await response.json();
        if (active && Array.isArray(data)) data.forEach(receive);
      } catch { /* A reconnect can retry without changing approval state. */ }
    };
    socket.on('mrw.actionRequired', receive);
    socket.on('mrw.actionResolved', resolved);
    socket.on('connect', refresh);
    void refresh();
    return () => {
      active = false;
      socket.off('mrw.actionRequired', receive);
      socket.off('mrw.actionResolved', resolved);
      socket.off('connect', refresh);
    };
  }, [threadId]);

  const action = actions.find((item) => item.threadId === threadId);
  if (!action) return null;
  const decide = async (approved: boolean) => {
    setBusy(action.actionId);
    setError('');
    try {
      const response = await fetch(withBasePath('/api/mrw/confirm'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getApiToken() ?? ''}`,
        },
        body: JSON.stringify({
          threadId: action.threadId, turnId: action.turnId, actionId: action.actionId,
          approved,
          userText: `approval:${action.actionId} ${approved ? 'Allow once' : 'Reject'} ${action.toolName}`,
        }),
      });
      if (!response.ok) throw new Error(`${t('Action confirmation failed')} (${response.status})`);
      setActions((items) => items.filter((item) => item.actionId !== action.actionId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('Action confirmation failed'));
    } finally {
      setBusy(null);
    }
  };
  return (
    <section className="shrink-0 border-b border-border px-4 py-3 text-sm" aria-label={t('Confirm action')}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <strong className="block">{t('Confirm action')}</strong>
          <code className="break-all">{action.toolName}</code>
          <div className="mt-1 break-all text-xs text-muted-foreground">
            {action.projectKey}{action.actionDigest ? ` · ${action.actionDigest.slice(0, 16)}` : ''}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void decide(false)}>
            <X className="size-4" />{t('Reject')}
          </Button>
          <Button size="sm" disabled={busy !== null} onClick={() => void decide(true)}>
            {busy === action.actionId ? <LoaderCircle className="size-4" /> : <Check className="size-4" />}
            {t('Allow once')}
          </Button>
        </div>
      </div>
      {action.arguments && (
        <details className="mt-2">
          <summary className="cursor-pointer text-muted-foreground">{t('Parameters')}</summary>
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all text-xs">
            {JSON.stringify(action.arguments, null, 2)}
          </pre>
        </details>
      )}
      {error && <p className="mt-2 text-destructive" role="alert">{error}</p>}
    </section>
  );
}
