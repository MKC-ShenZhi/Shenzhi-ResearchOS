import { apiJson, expectedUserHeaders } from "./http";
import type { CollectionPaperListResponse, KnowledgePaperDetail } from "@/clients/knowledge";

/**
 * 论文收藏/点赞与主题关注的服务端状态。
 *
 * 公开人数由服务端聚合；个人状态只按 BFF 注入的当前身份计算。卡片按需
 * 读取时先进入微批队列，同一事件循环内的所有卡片合并为一次请求（每批最多
 * 100 个 ID），避免列表页出现逐卡 N+1。公开人数与个人状态同请求返回，
 * 账号切换通过 identityKey 区分缓存。
 */

const MAX_BATCH_SIZE = 100;

export const PAPER_INTERACTION_CHANNEL = "shenzhi-paper-interactions";
export const TOPIC_INTERACTION_CHANNEL = "shenzhi-topic-interactions";

export interface PaperInteraction {
  paperId: string;
  collectorCount: number;
  likeCount: number;
  /** 仅登录身份返回；匿名时为 null。 */
  folderIds: number[] | null;
  liked: boolean | null;
}

export interface TopicInteraction {
  topicId: string;
  followerCount: number;
  isFollowing: boolean | null;
}

export interface LikeState {
  paperId: string;
  liked: boolean;
  likeCount: number;
}

export interface TopicFollowState {
  topicId: string;
  isFollowing: boolean;
  followerCount: number;
}

export interface LikedPaperItem extends KnowledgePaperDetail {
  paper_id: string;
  liked_at: string;
  is_available: boolean;
}

export interface LikedPaperListResponse {
  items: LikedPaperItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface FollowedTopicItem {
  topic_id: string;
  followed_at: string;
}

export interface TopicFollowListResponse {
  items: FollowedTopicItem[];
  total: number;
}

export const paperInteractionQueryKey = (identityKey: string, paperId: string) =>
  ["paper-interaction", identityKey, paperId] as const;

export const topicInteractionQueryKey = (identityKey: string, topicId: string) =>
  ["topic-interaction", identityKey, topicId] as const;

interface PaperInteractionDto {
  paper_id: string;
  collector_count: number;
  like_count: number;
  folder_ids: number[] | null;
  liked: boolean | null;
}

interface PaperInteractionsResponseDto {
  authenticated: boolean;
  user_id: string | null;
  items: PaperInteractionDto[];
}

interface TopicInteractionDto {
  topic_id: string;
  follower_count: number;
  is_following: boolean | null;
}

interface TopicInteractionsResponseDto {
  authenticated: boolean;
  user_id: string | null;
  items: TopicInteractionDto[];
}

interface LikeStateDto {
  paper_id: string;
  liked: boolean;
  like_count: number;
}

interface TopicFollowStateDto {
  topic_id: string;
  is_following: boolean;
  follower_count: number;
}

type Pending<T> = { resolve: (value: T) => void; reject: (error: unknown) => void };

const paperQueue = new Map<string, Map<string, Pending<PaperInteraction>[]>>();
const topicQueue = new Map<string, Map<string, Pending<TopicInteraction>[]>>();
let paperScheduled = false;
let topicScheduled = false;
let paperChannel: BroadcastChannel | undefined;
let topicChannel: BroadcastChannel | undefined;

function expectIdentity(identityKey: string, dto: { authenticated: boolean; user_id: string | null }) {
  const responseIdentity = dto.authenticated ? dto.user_id ?? null : null;
  if (responseIdentity !== (identityKey || null)) {
    throw new Error("互动状态所属账户已变化");
  }
}

async function requestPaperBatch(
  identityKey: string,
  entries: [string, Pending<PaperInteraction>[]][],
) {
  try {
    const response = await apiJson<PaperInteractionsResponseDto>("/papers/interactions", {
      method: "POST",
      body: JSON.stringify({ paper_ids: entries.map(([paperId]) => paperId) }),
    });
    expectIdentity(identityKey, response);
    const byId = new Map(response.items.map((item) => [item.paper_id, item]));
    for (const [paperId, waiters] of entries) {
      const item = byId.get(paperId);
      if (!item) throw new Error("互动状态响应不完整");
      const state: PaperInteraction = {
        paperId,
        collectorCount: item.collector_count,
        likeCount: item.like_count,
        folderIds: item.folder_ids,
        liked: item.liked,
      };
      for (const waiter of waiters) waiter.resolve(state);
    }
  } catch (error) {
    for (const [, waiters] of entries) {
      for (const waiter of waiters) waiter.reject(error);
    }
  }
}

async function requestTopicBatch(
  identityKey: string,
  entries: [string, Pending<TopicInteraction>[]][],
) {
  try {
    const response = await apiJson<TopicInteractionsResponseDto>("/topics/interactions", {
      method: "POST",
      body: JSON.stringify({ topic_ids: entries.map(([topicId]) => topicId) }),
    });
    expectIdentity(identityKey, response);
    const byId = new Map(response.items.map((item) => [item.topic_id, item]));
    for (const [topicId, waiters] of entries) {
      const item = byId.get(topicId);
      if (!item) throw new Error("互动状态响应不完整");
      const state: TopicInteraction = {
        topicId,
        followerCount: item.follower_count,
        isFollowing: item.is_following,
      };
      for (const waiter of waiters) waiter.resolve(state);
    }
  } catch (error) {
    for (const [, waiters] of entries) {
      for (const waiter of waiters) waiter.reject(error);
    }
  }
}

function flushPaperQueue() {
  paperScheduled = false;
  const queues = new Map(paperQueue);
  paperQueue.clear();
  for (const [identityKey, entries] of queues) {
    const list = [...entries.entries()];
    for (let index = 0; index < list.length; index += MAX_BATCH_SIZE) {
      void requestPaperBatch(identityKey, list.slice(index, index + MAX_BATCH_SIZE));
    }
  }
}

function flushTopicQueue() {
  topicScheduled = false;
  const queues = new Map(topicQueue);
  topicQueue.clear();
  for (const [identityKey, entries] of queues) {
    const list = [...entries.entries()];
    for (let index = 0; index < list.length; index += MAX_BATCH_SIZE) {
      void requestTopicBatch(identityKey, list.slice(index, index + MAX_BATCH_SIZE));
    }
  }
}

/** 读取单篇论文的收藏人数、点赞人数与当前身份状态。 */
export function fetchPaperInteraction(identityKey: string, paperId: string): Promise<PaperInteraction> {
  return new Promise((resolve, reject) => {
    const entries = paperQueue.get(identityKey) ?? new Map<string, Pending<PaperInteraction>[]>();
    const waiters = entries.get(paperId) ?? [];
    waiters.push({ resolve, reject });
    entries.set(paperId, waiters);
    paperQueue.set(identityKey, entries);
    if (!paperScheduled) {
      paperScheduled = true;
      setTimeout(flushPaperQueue, 0);
    }
  });
}

/** 读取单个主题的关注人数与当前身份状态。 */
export function fetchTopicInteraction(identityKey: string, topicId: string): Promise<TopicInteraction> {
  return new Promise((resolve, reject) => {
    const entries = topicQueue.get(identityKey) ?? new Map<string, Pending<TopicInteraction>[]>();
    const waiters = entries.get(topicId) ?? [];
    waiters.push({ resolve, reject });
    entries.set(topicId, waiters);
    topicQueue.set(identityKey, entries);
    if (!topicScheduled) {
      topicScheduled = true;
      setTimeout(flushTopicQueue, 0);
    }
  });
}

export async function likePaper(paperId: string, userId: string): Promise<LikeState> {
  const dto = await apiJson<LikeStateDto>(`/papers/${encodeURIComponent(paperId)}/like`, { method: "PUT", headers: expectedUserHeaders(userId) });
  return { paperId: dto.paper_id, liked: dto.liked, likeCount: dto.like_count };
}

export async function unlikePaper(paperId: string, userId: string): Promise<LikeState> {
  const dto = await apiJson<LikeStateDto>(`/papers/${encodeURIComponent(paperId)}/like`, { method: "DELETE", headers: expectedUserHeaders(userId) });
  return { paperId: dto.paper_id, liked: dto.liked, likeCount: dto.like_count };
}

export async function followTopic(topicId: string, userId: string): Promise<TopicFollowState> {
  const dto = await apiJson<TopicFollowStateDto>(
    `/topic-follows/${encodeURIComponent(topicId)}`,
    { method: "PUT", headers: expectedUserHeaders(userId) },
  );
  return { topicId: dto.topic_id, isFollowing: dto.is_following, followerCount: dto.follower_count };
}

export async function unfollowTopic(topicId: string, userId: string): Promise<TopicFollowState> {
  const dto = await apiJson<TopicFollowStateDto>(
    `/topic-follows/${encodeURIComponent(topicId)}`,
    { method: "DELETE", headers: expectedUserHeaders(userId) },
  );
  return { topicId: dto.topic_id, isFollowing: dto.is_following, followerCount: dto.follower_count };
}

export function fetchMyLikes(userId: string, page = 1, pageSize = 20): Promise<LikedPaperListResponse> {
  return apiJson<LikedPaperListResponse>(`/likes?page=${page}&page_size=${pageSize}`, { headers: expectedUserHeaders(userId) });
}

export function fetchMyCollectedPapers(userId: string, page = 1, pageSize = 20): Promise<CollectionPaperListResponse> {
  return apiJson<CollectionPaperListResponse>(`/collections/papers?page=${page}&page_size=${pageSize}`, { headers: expectedUserHeaders(userId) });
}

export function fetchMyTopicFollows(userId: string): Promise<TopicFollowListResponse> {
  return apiJson<TopicFollowListResponse>("/topic-follows", { headers: expectedUserHeaders(userId) });
}

/** 通知其他标签页/其他卡片同一篇论文的最新状态。 */
export function publishPaperInteraction(
  userId: string,
  update: { paperId: string; liked?: boolean; likeCount?: number; collectorCount?: number; folderIds?: number[] },
) {
  if (typeof BroadcastChannel === "undefined") return;
  paperChannel ??= new BroadcastChannel(PAPER_INTERACTION_CHANNEL);
  paperChannel.postMessage({ userId, ...update });
}

/** 通知其他标签页/其他卡片同一个主题的最新关注状态。 */
export function publishTopicInteraction(
  userId: string,
  update: { topicId: string; isFollowing?: boolean; followerCount?: number },
) {
  if (typeof BroadcastChannel === "undefined") return;
  topicChannel ??= new BroadcastChannel(TOPIC_INTERACTION_CHANNEL);
  topicChannel.postMessage({ userId, ...update });
}

/** Invalidate collection membership and lists in other tabs, including folder deletion. */
export function publishCollectionChange(userId: string, paperId?: string) {
  if (typeof BroadcastChannel === "undefined") return;
  paperChannel ??= new BroadcastChannel(PAPER_INTERACTION_CHANNEL);
  paperChannel.postMessage({ userId, paperId, collectionsChanged: true });
}
