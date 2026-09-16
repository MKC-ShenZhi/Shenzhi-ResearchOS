"use client";

import Image from "next/image";
import { useState } from "react";
import { ChevronDown, ChevronUp, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import type { UserProfile } from "@/clients/backend/profile";
import type { SettingsLocale } from "@/clients/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { AVATAR_OPTIONS, avatarPath } from "../../avatar-options";
import { useUserProfile } from "../../hooks/use-user-profile";

type SessionUser = { name?: string | null; email?: string | null; image?: string | null };
type Draft = Pick<UserProfile, "avatar_key" | "bio" | "achievements" | "educations" | "biography" | "institutions">;

const textareaClass = "w-full rounded-xl border border-line bg-card px-4 py-3 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15 disabled:opacity-50";

function draftFrom(profile: UserProfile): Draft {
  return {
    avatar_key: profile.avatar_key,
    bio: profile.bio,
    achievements: profile.achievements.map((item) => ({ ...item })),
    educations: profile.educations.map((item) => ({ ...item })),
    biography: profile.biography,
    institutions: profile.institutions.map((item) => ({ ...item })),
  };
}

function moveItem<T>(items: T[], index: number, offset: -1 | 1) {
  const target = index + offset;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function ItemActions({ index, length, onMove, onRemove, disabled }: {
  index: number;
  length: number;
  onMove: (offset: -1 | 1) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  return <div className="flex gap-1">
    <Button type="button" size="icon" variant="ghost" aria-label="上移" disabled={disabled || index === 0} onClick={() => onMove(-1)}><ChevronUp /></Button>
    <Button type="button" size="icon" variant="ghost" aria-label="下移" disabled={disabled || index === length - 1} onClick={() => onMove(1)}><ChevronDown /></Button>
    <Button type="button" size="icon" variant="ghost" aria-label="删除" disabled={disabled} onClick={onRemove}><Trash2 /></Button>
  </div>;
}

function EmptyState({ text }: { text: string }) {
  return <p className="rounded-xl bg-chip px-4 py-3 text-sm text-muted">{text}</p>;
}

export function ProfileEditor({ user, locale }: { user: SessionUser | null; locale: SettingsLocale }) {
  const { profile, loading, saving, error, save } = useUserProfile();
  const [editing, setEditing] = useState(false);
  const [draftState, setDraft] = useState<Draft | null>(null);
  const zh = locale === "zh-CN";

  if (!user) return <div className="mt-3 rounded-2xl bg-card p-6 text-sm text-muted shadow-card">{zh ? "登录后可编辑个人简介和学者画像。" : "Sign in to edit your profile and scholar portrait."}</div>;
  if (loading && !profile) return <div className="mt-3 rounded-2xl bg-card p-6 text-sm text-muted shadow-card">{zh ? "正在加载个人资料…" : "Loading profile…"}</div>;
  if (!profile) return <div className="mt-3 rounded-2xl bg-card p-6 shadow-card"><p role="alert" className="text-sm text-danger">{zh ? "个人资料加载失败，请刷新页面重试。" : "Could not load your profile. Refresh to retry."}</p></div>;

  const defaultAvatar = avatarPath(profile.avatar_key);
  const displayAvatar = profile.avatar_selected ? defaultAvatar : (user.image || defaultAvatar);
  const draft = draftState ?? draftFrom(profile);
  const cancel = () => { setDraft(null); setEditing(false); };
  const submit = async () => {
    const updated = await save(draft);
    if (updated) { setDraft(null); setEditing(false); }
  };

  return <div className="mt-3 space-y-6 rounded-2xl bg-card p-6 shadow-card">
    <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
      {/* eslint-disable-next-line @next/next/no-img-element -- may use an external Better Auth avatar URL. */}
      <img src={displayAvatar} alt={zh ? "当前头像" : "Current avatar"} className="size-24 shrink-0 rounded-2xl object-cover" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-ink">{user.name || user.email}</p>
        <p className="mt-1 text-sm text-muted">{user.email}</p>
        <p className="mt-2 text-xs text-muted">{zh ? "站内头像可从下方选择；本阶段不提供文件上传。" : "Choose a built-in avatar below. File upload is not available in this phase."}</p>
      </div>
      {!editing && <Button type="button" variant="outline" onClick={() => { setDraft(draftFrom(profile)); setEditing(true); }}><Pencil />{zh ? "编辑资料" : "Edit profile"}</Button>}
    </div>

    {editing ? <form className="space-y-7 border-t border-line pt-6" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <fieldset disabled={saving} className="space-y-7">
        <div><legend className="text-sm font-semibold text-ink">{zh ? "选择头像" : "Choose avatar"}</legend><div className="mt-3 grid grid-cols-5 gap-3">
          {AVATAR_OPTIONS.map((option) => <button key={option.key} type="button" aria-label={option.key} aria-pressed={draft.avatar_key === option.key} onClick={() => setDraft({ ...draft, avatar_key: option.key })} className={cn("rounded-xl p-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary", draft.avatar_key === option.key ? "bg-primary-soft ring-2 ring-primary" : "bg-chip")}><Image src={option.src} alt="" width={512} height={512} className="aspect-square w-full rounded-lg object-cover" /></button>)}
        </div></div>

        <label className="block space-y-2 text-sm font-semibold text-ink">{zh ? "个人简介" : "Short bio"}<textarea value={draft.bio} maxLength={500} rows={4} className={textareaClass} placeholder={zh ? "简要介绍研究方向和关注领域" : "Summarize your research interests"} onChange={(event) => setDraft({ ...draft, bio: event.target.value })} /><span className="block text-right text-xs font-normal text-muted">{draft.bio.length}/500</span></label>

        <div className="space-y-3"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-ink">{zh ? "成就" : "Achievements"}</h3><Button type="button" size="sm" variant="outline" disabled={draft.achievements.length >= 20} onClick={() => setDraft({ ...draft, achievements: [...draft.achievements, { title: "", detail: "", year: null }] })}><Plus />{zh ? "添加" : "Add"}</Button></div>
          {draft.achievements.length === 0 && <EmptyState text={zh ? "尚未添加成就。" : "No achievements yet."} />}
          {draft.achievements.map((item, index) => <div key={index} className="space-y-3 rounded-xl border border-line p-4"><div className="flex items-start gap-2"><div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-[1fr_110px]"><Input value={item.title} maxLength={160} required placeholder={zh ? "成就名称" : "Achievement title"} onChange={(event) => setDraft({ ...draft, achievements: draft.achievements.map((value, itemIndex) => itemIndex === index ? { ...value, title: event.target.value } : value) })} /><Input value={item.year ?? ""} inputMode="numeric" pattern="\d{4}" maxLength={4} placeholder={zh ? "年份" : "Year"} onChange={(event) => setDraft({ ...draft, achievements: draft.achievements.map((value, itemIndex) => itemIndex === index ? { ...value, year: event.target.value || null } : value) })} /></div><ItemActions index={index} length={draft.achievements.length} disabled={saving} onMove={(offset) => setDraft({ ...draft, achievements: moveItem(draft.achievements, index, offset) })} onRemove={() => setDraft({ ...draft, achievements: draft.achievements.filter((_, itemIndex) => itemIndex !== index) })} /></div><textarea value={item.detail} maxLength={500} rows={2} className={textareaClass} placeholder={zh ? "补充说明（可选）" : "Details (optional)"} onChange={(event) => setDraft({ ...draft, achievements: draft.achievements.map((value, itemIndex) => itemIndex === index ? { ...value, detail: event.target.value } : value) })} /></div>)}
        </div>

        <div className="space-y-3"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-ink">{zh ? "教育经历" : "Education"}</h3><Button type="button" size="sm" variant="outline" disabled={draft.educations.length >= 20} onClick={() => setDraft({ ...draft, educations: [...draft.educations, { institution: "", degree: "", field: "", start_year: null, end_year: null }] })}><Plus />{zh ? "添加" : "Add"}</Button></div>
          {draft.educations.length === 0 && <EmptyState text={zh ? "尚未添加教育经历。" : "No education history yet."} />}
          {draft.educations.map((item, index) => <div key={index} className="space-y-3 rounded-xl border border-line p-4"><div className="flex items-start gap-2"><div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2"><Input value={item.institution} maxLength={160} required placeholder={zh ? "学校或教育机构" : "Institution"} onChange={(event) => setDraft({ ...draft, educations: draft.educations.map((value, itemIndex) => itemIndex === index ? { ...value, institution: event.target.value } : value) })} /><Input value={item.degree} maxLength={120} placeholder={zh ? "学位" : "Degree"} onChange={(event) => setDraft({ ...draft, educations: draft.educations.map((value, itemIndex) => itemIndex === index ? { ...value, degree: event.target.value } : value) })} /><Input value={item.field} maxLength={120} placeholder={zh ? "专业或研究方向" : "Field"} onChange={(event) => setDraft({ ...draft, educations: draft.educations.map((value, itemIndex) => itemIndex === index ? { ...value, field: event.target.value } : value) })} /><div className="grid grid-cols-2 gap-3"><Input value={item.start_year ?? ""} inputMode="numeric" pattern="\d{4}" maxLength={4} placeholder={zh ? "开始年份" : "Start year"} onChange={(event) => setDraft({ ...draft, educations: draft.educations.map((value, itemIndex) => itemIndex === index ? { ...value, start_year: event.target.value || null } : value) })} /><Input value={item.end_year ?? ""} inputMode="numeric" pattern="\d{4}" maxLength={4} placeholder={zh ? "结束年份" : "End year"} onChange={(event) => setDraft({ ...draft, educations: draft.educations.map((value, itemIndex) => itemIndex === index ? { ...value, end_year: event.target.value || null } : value) })} /></div></div><ItemActions index={index} length={draft.educations.length} disabled={saving} onMove={(offset) => setDraft({ ...draft, educations: moveItem(draft.educations, index, offset) })} onRemove={() => setDraft({ ...draft, educations: draft.educations.filter((_, itemIndex) => itemIndex !== index) })} /></div></div>)}
        </div>

        <label className="block space-y-2 text-sm font-semibold text-ink">{zh ? "生平" : "Biography"}<textarea value={draft.biography} maxLength={4000} rows={7} className={textareaClass} placeholder={zh ? "填写学习、研究或职业经历的完整说明" : "Describe your academic and professional journey"} onChange={(event) => setDraft({ ...draft, biography: event.target.value })} /><span className="block text-right text-xs font-normal text-muted">{draft.biography.length}/4000</span></label>

        <div className="space-y-3"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-ink">{zh ? "机构经历" : "Institutions"}</h3><Button type="button" size="sm" variant="outline" disabled={draft.institutions.length >= 20} onClick={() => setDraft({ ...draft, institutions: [...draft.institutions, { name: "", role: "", start_year: null, end_year: null }] })}><Plus />{zh ? "添加" : "Add"}</Button></div>
          {draft.institutions.length === 0 && <EmptyState text={zh ? "尚未添加机构经历。" : "No institution history yet."} />}
          {draft.institutions.map((item, index) => <div key={index} className="flex items-start gap-2 rounded-xl border border-line p-4"><div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2"><Input value={item.name} maxLength={160} required placeholder={zh ? "机构名称" : "Institution name"} onChange={(event) => setDraft({ ...draft, institutions: draft.institutions.map((value, itemIndex) => itemIndex === index ? { ...value, name: event.target.value } : value) })} /><Input value={item.role} maxLength={120} placeholder={zh ? "职务或身份" : "Role"} onChange={(event) => setDraft({ ...draft, institutions: draft.institutions.map((value, itemIndex) => itemIndex === index ? { ...value, role: event.target.value } : value) })} /><Input value={item.start_year ?? ""} inputMode="numeric" pattern="\d{4}" maxLength={4} placeholder={zh ? "开始年份" : "Start year"} onChange={(event) => setDraft({ ...draft, institutions: draft.institutions.map((value, itemIndex) => itemIndex === index ? { ...value, start_year: event.target.value || null } : value) })} /><Input value={item.end_year ?? ""} inputMode="numeric" pattern="\d{4}" maxLength={4} placeholder={zh ? "结束年份" : "End year"} onChange={(event) => setDraft({ ...draft, institutions: draft.institutions.map((value, itemIndex) => itemIndex === index ? { ...value, end_year: event.target.value || null } : value) })} /></div><ItemActions index={index} length={draft.institutions.length} disabled={saving} onMove={(offset) => setDraft({ ...draft, institutions: moveItem(draft.institutions, index, offset) })} onRemove={() => setDraft({ ...draft, institutions: draft.institutions.filter((_, itemIndex) => itemIndex !== index) })} /></div>)}
        </div>
      </fieldset>
      {error === "save" && <p role="alert" className="text-sm text-danger">{zh ? "保存失败，草稿已保留，请稍后重试。" : "Save failed. Your draft is preserved; try again."}</p>}
      <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={saving} onClick={cancel}><X />{zh ? "取消" : "Cancel"}</Button><Button type="submit" disabled={saving}><Save />{saving ? (zh ? "保存中…" : "Saving…") : (zh ? "保存资料" : "Save profile")}</Button></div>
    </form> : <div className="grid gap-6 border-t border-line pt-6 lg:grid-cols-2">
      <section><h3 className="text-sm font-semibold text-ink">{zh ? "个人简介" : "Short bio"}</h3><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted">{profile.bio || (zh ? "尚未填写个人简介。" : "No short bio yet.")}</p></section>
      <section><h3 className="text-sm font-semibold text-ink">{zh ? "成就" : "Achievements"}</h3>{profile.achievements.length ? <ul className="mt-2 space-y-2">{profile.achievements.map((item, index) => <li key={index} className="text-sm text-muted"><span className="font-medium text-ink-2">{item.title}</span>{item.year && ` · ${item.year}`}{item.detail && <p className="mt-1">{item.detail}</p>}</li>)}</ul> : <p className="mt-2 text-sm text-muted">{zh ? "尚未添加成就。" : "No achievements yet."}</p>}</section>
      <section><h3 className="text-sm font-semibold text-ink">{zh ? "教育经历" : "Education"}</h3>{profile.educations.length ? <ul className="mt-2 space-y-2">{profile.educations.map((item, index) => <li key={index} className="text-sm text-muted"><span className="font-medium text-ink-2">{item.institution}</span><p>{[item.degree, item.field, [item.start_year, item.end_year].filter(Boolean).join("–")].filter(Boolean).join(" · ")}</p></li>)}</ul> : <p className="mt-2 text-sm text-muted">{zh ? "尚未添加教育经历。" : "No education history yet."}</p>}</section>
      <section><h3 className="text-sm font-semibold text-ink">{zh ? "机构经历" : "Institutions"}</h3>{profile.institutions.length ? <ul className="mt-2 space-y-2">{profile.institutions.map((item, index) => <li key={index} className="text-sm text-muted"><span className="font-medium text-ink-2">{item.name}</span><p>{[item.role, [item.start_year, item.end_year].filter(Boolean).join("–")].filter(Boolean).join(" · ")}</p></li>)}</ul> : <p className="mt-2 text-sm text-muted">{zh ? "尚未添加机构经历。" : "No institution history yet."}</p>}</section>
      <section className="lg:col-span-2"><h3 className="text-sm font-semibold text-ink">{zh ? "生平" : "Biography"}</h3><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted">{profile.biography || (zh ? "尚未填写生平。" : "No biography yet.")}</p></section>
    </div>}
  </div>;
}
