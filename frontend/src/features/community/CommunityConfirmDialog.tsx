import type { ReactNode } from 'react';

type CommunityConfirmDialogProps = {
  confirmLabel?: string;
  description: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
  pendingLabel?: string;
  submitting?: boolean;
  title: string;
  titleId: string;
  tone?: 'danger' | 'primary';
};

export function CommunityConfirmDialog({
  confirmLabel = '删除',
  description,
  onCancel,
  onConfirm,
  pendingLabel = '正在处理',
  submitting = false,
  title,
  titleId,
  tone = 'danger',
}: CommunityConfirmDialogProps) {
  return (
    <div className="community-overlay community-confirm-overlay" role="presentation" onMouseDown={() => { if (!submitting) onCancel(); }}>
      <section className="community-delete-dialog community-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} onMouseDown={(event) => event.stopPropagation()}>
        <h2 id={titleId}>{title}</h2>
        <p>{description}</p>
        <footer>
          <button type="button" disabled={submitting} onClick={onCancel}>取消</button>
          <button type="button" className={tone === 'danger' ? 'danger' : 'community-confirm-primary'} disabled={submitting} onClick={onConfirm}>
            {submitting ? pendingLabel : confirmLabel}
          </button>
        </footer>
      </section>
    </div>
  );
}
