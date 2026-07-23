import type { ApiCommunityAuthor, ApiCommunityCaseUpdate, CommunityPostType } from './types';

export function formatCommunityIdentity(value: ApiCommunityAuthor['identity_type']) {
  return ({ farmer: '养殖户', technician: '农技人员', researcher: '科研人员', other: '行业从业者' } as const)[value];
}

export function formatCommunityTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '刚刚';
  const elapsed = Date.now() - date.getTime();
  if (elapsed < 60_000) return '刚刚';
  if (elapsed < 3_600_000) return `${Math.max(1, Math.floor(elapsed / 60_000))} 分钟前`;
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)} 小时前`;
  if (elapsed < 7 * 86_400_000) return `${Math.floor(elapsed / 86_400_000)} 天前`;
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(date);
}

export function formatCommunityPostType(value: CommunityPostType) {
  return { experience: '经验分享', case: '病例交流', question: '提问求助', reference: '资料解读', announcement: '公告' }[value];
}

export function formatCaseUpdateStatus(value: ApiCommunityCaseUpdate['outcome_status']) {
  return ({ observing: '继续观察', improved: '已有改善', stable: '情况稳定', worsened: '有所加重', resolved: '问题解决' } as const)[value];
}

export function formatNotificationText(value: string, payload?: Record<string, unknown>) {
  if (value === 'moderation' && typeof payload?.message === 'string' && payload.message.trim()) {
    return ` ${payload.message.trim()}`;
  }
  return { post_like: ' 赞了你的帖子', post_comment: ' 评论了你的帖子', comment_reply: ' 回复了你的评论', comment_like: ' 赞了你的评论', follow: ' 关注了你', moderation: ' 更新了审核状态', answer_accepted: ' 采纳了你的回答', case_update: ' 更新了病例随访', mention: ' 在社区内容中提到了你', direct_message: ' 向你发送了一条私信' }[value] ?? ' 与你互动';
}
