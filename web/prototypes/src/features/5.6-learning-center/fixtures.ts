export type CourseStatus = "draft" | "published" | "unpublished";
export type Visibility = "all" | "assigned";
export type MaterialType = "video" | "audio" | "pdf";
export type LearnStatus = "not_started" | "in_progress" | "completed";
export type TranscodeStatus = "ok" | "processing" | "failed";

export const COURSE_STATUS_LABEL: Record<CourseStatus, string> = {
  draft: "草稿",
  published: "已上架",
  unpublished: "已下架",
};

export const VISIBILITY_LABEL: Record<Visibility, string> = {
  all: "全员",
  assigned: "指定学员",
};

export const LEARN_STATUS_LABEL: Record<LearnStatus, string> = {
  not_started: "未开始",
  in_progress: "学习中",
  completed: "已完成",
};

export interface AdminCourse {
  id: string;
  name: string;
  status: CourseStatus;
  visibility: Visibility;
  sectionCount: number;
  materialCount: number;
  learnerText: string;
  completedCount: number;
  updatedAt: string;
}

export interface MyCourse {
  id: string;
  name: string;
  intro: string;
  materialCount: number;
  progress: number;
  status: LearnStatus;
}

export interface Material {
  id: string;
  name: string;
  type: MaterialType;
  duration?: string;
  done?: boolean;
  transcode?: TranscodeStatus;
}

export interface Section {
  id: string;
  name: string;
  materials: Material[];
}

export interface Learner {
  id: string;
  name: string;
  group: string;
  sourceText: string;
  directAssigned: boolean;
  progress: number;
  status: LearnStatus;
  lastLearnAt: string | null;
}

/** Assignment target shown as a removable tag in the members tab. */
export interface AssignTarget {
  id: string;
  type: "group" | "employee";
  name: string;
  detail: string;
}

/** Group row in the add-learners dialog (dynamic assignment). */
export interface PickerGroup {
  id: string;
  name: string;
  memberCount: number;
  added?: boolean;
}

export interface PickerEmployee {
  id: string;
  name: string;
  group: string;
  assigned?: boolean;
}

export const ADMIN_COURSES: AdminCourse[] = [
  {
    id: "c-1",
    name: "新员工入职培训",
    status: "published",
    visibility: "all",
    sectionCount: 3,
    materialCount: 8,
    learnerText: "全员",
    completedCount: 21,
    updatedAt: "2026-08-06 14:20",
  },
  {
    id: "c-2",
    name: "呼叫中心标准话术（8 月版）",
    status: "published",
    visibility: "assigned",
    sectionCount: 2,
    materialCount: 5,
    learnerText: "18",
    completedCount: 9,
    updatedAt: "2026-08-05 17:42",
  },
  {
    id: "c-3",
    name: "新产品套餐知识速成",
    status: "draft",
    visibility: "assigned",
    sectionCount: 1,
    materialCount: 3,
    learnerText: "6",
    completedCount: 0,
    updatedAt: "2026-08-07 10:15",
  },
  {
    id: "c-4",
    name: "客户投诉处理进阶",
    status: "unpublished",
    visibility: "assigned",
    sectionCount: 2,
    materialCount: 6,
    learnerText: "12",
    completedCount: 11,
    updatedAt: "2026-07-28 09:30",
  },
  {
    id: "c-5",
    name: "服务红线与合规必读",
    status: "published",
    visibility: "all",
    sectionCount: 1,
    materialCount: 2,
    learnerText: "全员",
    completedCount: 47,
    updatedAt: "2026-08-01 11:08",
  },
];

export const MY_COURSES: MyCourse[] = [
  {
    id: "c-2",
    name: "呼叫中心标准话术（8 月版）",
    intro: "覆盖开场白、异议处理与结束语三段标准话术，含通话录音示例与逐句拆解。",
    materialCount: 5,
    progress: 60,
    status: "in_progress",
  },
  {
    id: "c-1",
    name: "新员工入职培训",
    intro: "公司介绍、客服系统基础操作与服务规范，帮助新同学第一周快速上手。",
    materialCount: 8,
    progress: 0,
    status: "not_started",
  },
  {
    id: "c-5",
    name: "服务红线与合规必读",
    intro: "服务禁语、隐私保护与投诉升级红线，全员必修。",
    materialCount: 2,
    progress: 100,
    status: "completed",
  },
  {
    id: "c-6",
    name: "工单流转与升级规则",
    intro: "工单创建、流转、升级与关闭的标准流程说明。",
    materialCount: 4,
    progress: 25,
    status: "in_progress",
  },
];

export const COURSE_NAME = "呼叫中心标准话术（8 月版）";

export const COURSE_SECTIONS: Section[] = [
  {
    id: "s-1",
    name: "第一章 · 开场与破冰",
    materials: [
      { id: "m-1", name: "标准开场白讲解", type: "video", duration: "08:24", done: true, transcode: "ok" },
      { id: "m-2", name: "开场白示范录音", type: "audio", duration: "03:12", done: true },
      { id: "m-3", name: "开场白速查卡", type: "pdf", done: true },
    ],
  },
  {
    id: "s-2",
    name: "第二章 · 异议处理",
    materials: [
      { id: "m-4", name: "价格异议处理示范", type: "video", duration: "12:05", transcode: "ok" },
      { id: "m-5", name: "常见异议应对手册", type: "pdf" },
      { id: "m-6", name: "情绪安抚技巧", type: "audio", duration: "06:48" },
    ],
  },
  {
    id: "s-3",
    name: "第三章 · 结束语与跟进",
    materials: [
      { id: "m-7", name: "结束语与满意度引导", type: "video", duration: "05:36", transcode: "processing" },
      { id: "m-8", name: "跟进话术模板", type: "pdf" },
    ],
  },
];

/** Chapter/material list on the course edit page, with upload and transcode states. */
export const EDIT_SECTIONS: Section[] = [
  {
    id: "s-1",
    name: "第一章 · 开场与破冰",
    materials: [
      { id: "m-1", name: "标准开场白讲解", type: "video", duration: "08:24", transcode: "ok" },
      { id: "m-2", name: "开场白示范录音", type: "audio", duration: "03:12" },
      { id: "m-3", name: "开场白速查卡", type: "pdf" },
    ],
  },
  {
    id: "s-2",
    name: "第二章 · 异议处理",
    materials: [
      { id: "m-4", name: "价格异议处理示范", type: "video", duration: "12:05", transcode: "processing" },
      { id: "m-5", name: "客户情绪安抚实录", type: "video", duration: "09:51", transcode: "failed" },
    ],
  },
];

export const LEARNERS: Learner[] = [
  { id: "e-1", name: "张敏", group: "客服一组", sourceText: "组：客服一组", directAssigned: false, progress: 100, status: "completed", lastLearnAt: "2026-08-06 16:20" },
  { id: "e-2", name: "李悦", group: "客服一组", sourceText: "组：客服一组 + 直接指派", directAssigned: true, progress: 60, status: "in_progress", lastLearnAt: "2026-08-07 09:12" },
  { id: "e-3", name: "周凯", group: "客服二组", sourceText: "组：客服二组", directAssigned: false, progress: 40, status: "in_progress", lastLearnAt: "2026-08-05 15:44" },
  { id: "e-4", name: "王芳", group: "客服二组", sourceText: "组：客服二组", directAssigned: false, progress: 100, status: "completed", lastLearnAt: "2026-08-04 11:02" },
  { id: "e-5", name: "陈晨", group: "售后支持组", sourceText: "直接指派", directAssigned: true, progress: 0, status: "not_started", lastLearnAt: null },
  { id: "e-6", name: "刘畅", group: "售后支持组", sourceText: "直接指派", directAssigned: true, progress: 20, status: "in_progress", lastLearnAt: "2026-08-07 14:37" },
];

export const ALL_EMPLOYEES_PROGRESS: Learner[] = [
  ...LEARNERS,
  { id: "e-7", name: "赵一鸣", group: "客服一组", sourceText: "全员", directAssigned: false, progress: 0, status: "not_started", lastLearnAt: null },
  { id: "e-8", name: "孙可", group: "新入职（未分组）", sourceText: "全员", directAssigned: false, progress: 0, status: "not_started", lastLearnAt: null },
];

export const ASSIGN_TARGETS: AssignTarget[] = [
  { id: "g-1", type: "group", name: "客服一组", detail: "在职成员 12 人" },
  { id: "g-2", type: "group", name: "客服二组", detail: "在职成员 9 人" },
  { id: "e-6", type: "employee", name: "刘畅", detail: "售后支持组" },
  { id: "e-5", type: "employee", name: "陈晨", detail: "售后支持组" },
];

export const ASSIGN_GROUP_OPTIONS: PickerGroup[] = [
  { id: "g-1", name: "客服一组", memberCount: 12, added: true },
  { id: "g-2", name: "客服二组", memberCount: 9, added: true },
  { id: "g-3", name: "售后支持组", memberCount: 7 },
  { id: "g-4", name: "质检组", memberCount: 4 },
];

export const PICKER_EMPLOYEES: PickerEmployee[] = [
  { id: "e-1", name: "张敏", group: "客服一组", assigned: true },
  { id: "e-2", name: "李悦", group: "客服一组", assigned: true },
  { id: "e-9", name: "吴迪", group: "客服一组" },
  { id: "e-10", name: "郑爽", group: "客服二组" },
  { id: "e-11", name: "冯远", group: "客服二组" },
  { id: "e-12", name: "许静", group: "售后支持组" },
  { id: "e-13", name: "何斌", group: "售后支持组" },
  { id: "e-14", name: "罗晓", group: "新入职（未分组）" },
];

