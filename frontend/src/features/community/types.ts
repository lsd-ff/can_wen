export type CommunityFeedTab = 'recommended' | 'following' | 'topics' | 'latest' | 'bookmarked' | 'liked' | 'history' | 'mine' | 'drafts';
export type CommunityConfirmAction = 'clear_history' | 'reset_recommendations';
export type CommunityPostType = 'experience' | 'case' | 'question' | 'reference' | 'announcement';
export type CommunityPostVisibility = 'public' | 'followers';
export type CommunityRelationshipType = 'followers' | 'following';

export type ApiCommunityAuthor = {
  id: string;
  display_name: string;
  username: string;
  avatar_url: string | null;
  role: string;
  is_followed: boolean;
  identity_type: 'farmer' | 'technician' | 'researcher' | 'other';
  region: string | null;
  organization: string | null;
  expertise_tags: string[];
  years_experience: number | null;
  bio: string | null;
  verification_status: 'unverified' | 'pending' | 'verified' | 'rejected';
  post_count: number;
  follower_count: number;
  following_count: number;
  received_like_count: number;
};

export type ApiCommunityCaseUpdate = {
  id: string;
  post_id: string;
  occurred_on: string;
  outcome_status: 'observing' | 'improved' | 'stable' | 'worsened' | 'resolved';
  content: string;
  metrics: Record<string, unknown>;
  author: ApiCommunityAuthor;
  created_at: string;
};

export type ApiCommunityAsset = {
  id: string;
  file_id: string;
  file_name: string;
  file_type: 'image' | 'video' | 'document' | 'audio' | 'other';
  mime_type: string;
  storage_url: string | null;
  file_size: number;
  asset_role: 'attachment' | 'cover';
  sort_order: number;
};

export type ApiCommunityUpload = {
  file_id: string;
  file_name: string;
  file_type: 'image' | 'video' | 'document' | 'audio' | 'other';
  mime_type: string;
  storage_url: string | null;
  file_size: number;
};

export type ApiCommunityTag = {
  id: string;
  name: string;
  post_count: number;
  is_followed: boolean;
};

export type ApiCommunityPost = {
  id: string;
  title: string;
  content_markdown: string;
  excerpt: string;
  post_type: CommunityPostType;
  visibility: CommunityPostVisibility;
  status: 'draft' | 'published' | 'hidden' | 'deleted';
  source_conversation_id: string | null;
  source_husbandry_case_id: string | null;
  accepted_comment_id: string | null;
  question_status: 'open' | 'resolved';
  case_data: Record<string, string | number | null>;
  case_updates: ApiCommunityCaseUpdate[];
  author: ApiCommunityAuthor;
  tags: ApiCommunityTag[];
  assets: ApiCommunityAsset[];
  like_count: number;
  bookmark_count: number;
  comment_count: number;
  view_count: number;
  is_liked: boolean;
  is_bookmarked: boolean;
  is_author: boolean;
  recommendation_reason: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
};

export type ApiCommunityPostList = {
  items: ApiCommunityPost[];
  next_offset: number | null;
};

export type ApiCommunityBookmarkCollection = {
  id: string;
  name: string;
  description: string | null;
  item_count: number;
  contains_post: boolean;
  created_at: string;
  updated_at: string;
};

export type ApiCommunityBookmarkCollectionList = {
  items: ApiCommunityBookmarkCollection[];
};

export type ApiCommunityBookmarkCollectionDetail = {
  collection: ApiCommunityBookmarkCollection;
  posts: ApiCommunityPost[];
  next_offset: number | null;
};

export type ApiCommunityComment = {
  id: string;
  post_id: string;
  parent_comment_id: string | null;
  content: string;
  status: string;
  like_count: number;
  is_liked: boolean;
  is_author: boolean;
  is_accepted: boolean;
  author: ApiCommunityAuthor;
  created_at: string;
  updated_at: string;
};

export type ApiCommunityCommentList = {
  items: ApiCommunityComment[];
  next_offset: number | null;
};

export type ApiCommunityNotification = {
  id: string;
  notification_type: string;
  post_id: string | null;
  comment_id: string | null;
  actor: ApiCommunityAuthor | null;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
};

export type ApiCommunityNotifications = {
  items: ApiCommunityNotification[];
  unread_count: number;
};

export type CommunityRealtimeEvent = {
  type: 'notification' | 'ready' | string;
  notification_type?: string;
  post_id?: string | null;
  comment_id?: string | null;
  payload?: Record<string, unknown>;
};

export type ApiCommunityReport = {
  id: string;
  target_type: 'post' | 'comment';
  post_id: string | null;
  comment_id: string | null;
  reason: string;
  detail: string | null;
  status: 'pending' | 'reviewed' | 'dismissed';
  reporter: ApiCommunityAuthor;
  created_at: string;
  reviewed_at: string | null;
};

export type ApiCommunityProfileDetail = {
  author: ApiCommunityAuthor;
  posts: ApiCommunityPost[];
  next_offset: number | null;
};

export type ApiCommunityCreatorOverview = {
  post_count: number;
  published_this_week: number;
  view_count: number;
  received_like_count: number;
  bookmark_count: number;
  comment_count: number;
  follower_count: number;
  following_count: number;
};

export type ApiCommunityRelationshipList = {
  author: ApiCommunityAuthor;
  relationship_type: CommunityRelationshipType;
  items: ApiCommunityAuthor[];
  next_offset: number | null;
};

export type ApiCommunityBlockedUserList = {
  items: ApiCommunityAuthor[];
  next_offset: number | null;
};

export type ApiCommunityDirectThread = {
  id: string;
  counterpart: ApiCommunityAuthor;
  last_message_preview: string;
  last_message_at: string;
  unread_count: number;
};

export type ApiCommunityDirectMessage = {
  id: string;
  thread_id: string;
  sender_id: string;
  recipient_id: string;
  content: string;
  status: 'active' | 'deleted';
  is_mine: boolean;
  read_at: string | null;
  created_at: string;
};

export type ApiCommunitySearch = {
  posts: ApiCommunityPost[];
  authors: ApiCommunityAuthor[];
  tags: ApiCommunityTag[];
};
