export type ExamStatus = "draft" | "published" | "unpublished";
export type Visibility = "all" | "assigned";
export type ExamResultStatus = "not_started" | "passed" | "failed";
export type QuestionType = "single" | "multiple" | "judge";

export const EXAM_STATUS_LABEL: Record<ExamStatus, string> = {
  draft: "草稿",
  published: "已上架",
  unpublished: "已下架",
};

export const VISIBILITY_LABEL: Record<Visibility, string> = {
  all: "全员",
  assigned: "指定学员",
};

export const RESULT_STATUS_LABEL: Record<ExamResultStatus, string> = {
  not_started: "未开始",
  passed: "已通过",
  failed: "未通过",
};

export const QUESTION_TYPE_LABEL: Record<QuestionType, string> = {
  single: "单选题",
  multiple: "多选题",
  judge: "判断题",
};

export interface AdminExam {
  id: string;
  name: string;
  status: ExamStatus;
  visibility: Visibility;
  questionCount: number;
  totalScore: number;
  passScore: number;
  passPercent: number;
  learnerText: string;
  passedCount: number;
  updatedAt: string;
}

export interface MyExam {
  id: string;
  name: string;
  intro: string;
  totalScore: number;
  bestScore: number | null;
  status: ExamResultStatus;
  remainingAttempts: number;
  maxAttempts: number;
  timeLimitMinutes: number | null;
}

export interface QuestionOption {
  id: string;
  text: string;
  correct?: boolean;
}

export interface Question {
  id: string;
  type: QuestionType;
  stem: string;
  score: number;
  options: QuestionOption[];
}

export interface Candidate {
  id: string;
  name: string;
  group: string;
  sourceText: string;
  directAssigned: boolean;
  bestScore: number | null;
  status: ExamResultStatus;
  attemptCount: number;
  lastSubmitAt: string | null;
}

export interface AssignTarget {
  id: string;
  type: "group" | "employee";
  name: string;
  detail: string;
}

export interface AttemptSummary {
  id: string;
  index: number;
  score: number;
  totalScore: number;
  passed: boolean;
  submittedAt: string;
  durationText: string;
}

export interface ReviewQuestion extends Question {
  selectedIds: string[];
  earned: number;
}

export const EXAM_NAME = "呼叫中心标准话术考核（8 月版）";

export const ADMIN_EXAMS: AdminExam[] = [
  {
    id: "x-1",
    name: "呼叫中心标准话术考核（8 月版）",
    status: "published",
    visibility: "assigned",
    questionCount: 10,
    totalScore: 100,
    passScore: 60,
    passPercent: 60,
    learnerText: "18",
    passedCount: 11,
    updatedAt: "2026-08-06 16:40",
  },
  {
    id: "x-2",
    name: "服务红线与合规测验",
    status: "published",
    visibility: "all",
    questionCount: 8,
    totalScore: 80,
    passScore: 64,
    passPercent: 80,
    learnerText: "全员",
    passedCount: 39,
    updatedAt: "2026-08-05 11:20",
  },
  {
    id: "x-3",
    name: "新产品套餐知识测验",
    status: "draft",
    visibility: "assigned",
    questionCount: 6,
    totalScore: 60,
    passScore: 36,
    passPercent: 60,
    learnerText: "6",
    passedCount: 0,
    updatedAt: "2026-08-07 09:55",
  },
  {
    id: "x-4",
    name: "入职基础操作考核",
    status: "unpublished",
    visibility: "assigned",
    questionCount: 12,
    totalScore: 100,
    passScore: 70,
    passPercent: 70,
    learnerText: "24",
    passedCount: 20,
    updatedAt: "2026-07-30 18:10",
  },
];

export const MY_EXAMS: MyExam[] = [
  {
    id: "x-1",
    name: "呼叫中心标准话术考核（8 月版）",
    intro: "覆盖开场白、异议处理与结束语关键知识点，满分 100，及格 60。",
    totalScore: 100,
    bestScore: 72,
    status: "passed",
    remainingAttempts: 1,
    maxAttempts: 2,
    timeLimitMinutes: 30,
  },
  {
    id: "x-2",
    name: "服务红线与合规测验",
    intro: "服务禁语、隐私保护与投诉升级红线，全员必考。",
    totalScore: 80,
    bestScore: 48,
    status: "failed",
    remainingAttempts: 1,
    maxAttempts: 2,
    timeLimitMinutes: 20,
  },
  {
    id: "x-5",
    name: "工单流转规则小测",
    intro: "工单创建、流转、升级与关闭的标准规则抽查。",
    totalScore: 50,
    bestScore: null,
    status: "not_started",
    remainingAttempts: 1,
    maxAttempts: 1,
    timeLimitMinutes: null,
  },
  {
    id: "x-6",
    name: "质检评分标准认知",
    intro: "了解质检扣分项与优秀案例标准。",
    totalScore: 60,
    bestScore: 55,
    status: "failed",
    remainingAttempts: 0,
    maxAttempts: 2,
    timeLimitMinutes: 15,
  },
];

export const EDIT_QUESTIONS: Question[] = [
  {
    id: "q-1",
    type: "single",
    stem: "客户接通后，标准开场白应首先确认哪一项信息？",
    score: 10,
    options: [
      { id: "a", text: "客户姓名或称呼", correct: true },
      { id: "b", text: "客户银行卡号" },
      { id: "c", text: "客户家庭住址" },
      { id: "d", text: "客户同事电话" },
    ],
  },
  {
    id: "q-2",
    type: "multiple",
    stem: "处理价格异议时，以下哪些做法是正确的？（多选）",
    score: 15,
    options: [
      { id: "a", text: "先共情再解释价值", correct: true },
      { id: "b", text: "直接承诺私自降价", correct: false },
      { id: "c", text: "提供可选方案供客户比较", correct: true },
      { id: "d", text: "打断客户并强调公司规定", correct: false },
    ],
  },
  {
    id: "q-3",
    type: "judge",
    stem: "未经客户同意，可以向第三方透露客户手机号。",
    score: 10,
    options: [
      { id: "true", text: "正确", correct: false },
      { id: "false", text: "错误", correct: true },
    ],
  },
  {
    id: "q-4",
    type: "single",
    stem: "通话结束前，建议引导客户完成哪项动作？",
    score: 10,
    options: [
      { id: "a", text: "满意度评价", correct: true },
      { id: "b", text: "转发宣传海报" },
      { id: "c", text: "下载无关 App" },
      { id: "d", text: "提供家庭成员信息" },
    ],
  },
  {
    id: "q-5",
    type: "multiple",
    stem: "以下属于服务红线的行为有哪些？（多选）",
    score: 15,
    options: [
      { id: "a", text: "辱骂客户", correct: true },
      { id: "b", text: "伪造工单处理结果", correct: true },
      { id: "c", text: "按规定升级投诉", correct: false },
      { id: "d", text: "私下向客户索要红包", correct: true },
    ],
  },
];

/** Taking screen shows a subset with some answers selected (static state). */
export const TAKING_QUESTIONS: Question[] = EDIT_QUESTIONS.slice(0, 4);

export const REVIEW_QUESTIONS: ReviewQuestion[] = [
  {
    ...EDIT_QUESTIONS[0],
    selectedIds: ["a"],
    earned: 10,
  },
  {
    ...EDIT_QUESTIONS[1],
    selectedIds: ["a", "c"],
    earned: 15,
  },
  {
    ...EDIT_QUESTIONS[2],
    selectedIds: ["true"],
    earned: 0,
  },
  {
    ...EDIT_QUESTIONS[3],
    selectedIds: ["a"],
    earned: 10,
  },
  {
    ...EDIT_QUESTIONS[4],
    selectedIds: ["a", "b"],
    earned: 0,
  },
];

export const ATTEMPT_HISTORY: AttemptSummary[] = [
  {
    id: "att-2",
    index: 2,
    score: 72,
    totalScore: 100,
    passed: true,
    submittedAt: "2026-08-07 15:18",
    durationText: "18 分 22 秒",
  },
  {
    id: "att-1",
    index: 1,
    score: 55,
    totalScore: 100,
    passed: false,
    submittedAt: "2026-08-06 10:05",
    durationText: "24 分 01 秒",
  },
];

export const CANDIDATES: Candidate[] = [
  {
    id: "e-1",
    name: "张敏",
    group: "客服一组",
    sourceText: "组：客服一组",
    directAssigned: false,
    bestScore: 88,
    status: "passed",
    attemptCount: 1,
    lastSubmitAt: "2026-08-06 16:20",
  },
  {
    id: "e-2",
    name: "李悦",
    group: "客服一组",
    sourceText: "组：客服一组 + 直接指派",
    directAssigned: true,
    bestScore: 72,
    status: "passed",
    attemptCount: 2,
    lastSubmitAt: "2026-08-07 15:18",
  },
  {
    id: "e-3",
    name: "周凯",
    group: "客服二组",
    sourceText: "组：客服二组",
    directAssigned: false,
    bestScore: 48,
    status: "failed",
    attemptCount: 1,
    lastSubmitAt: "2026-08-05 15:44",
  },
  {
    id: "e-4",
    name: "王芳",
    group: "客服二组",
    sourceText: "组：客服二组",
    directAssigned: false,
    bestScore: 90,
    status: "passed",
    attemptCount: 1,
    lastSubmitAt: "2026-08-04 11:02",
  },
  {
    id: "e-5",
    name: "陈晨",
    group: "售后支持组",
    sourceText: "直接指派",
    directAssigned: true,
    bestScore: null,
    status: "not_started",
    attemptCount: 0,
    lastSubmitAt: null,
  },
  {
    id: "e-6",
    name: "刘畅",
    group: "售后支持组",
    sourceText: "直接指派",
    directAssigned: true,
    bestScore: 60,
    status: "passed",
    attemptCount: 2,
    lastSubmitAt: "2026-08-07 14:37",
  },
];

export const ASSIGN_TARGETS: AssignTarget[] = [
  { id: "g-1", type: "group", name: "客服一组", detail: "在职成员 12 人" },
  { id: "g-2", type: "group", name: "客服二组", detail: "在职成员 9 人" },
  { id: "e-6", type: "employee", name: "刘畅", detail: "售后支持组" },
  { id: "e-5", type: "employee", name: "陈晨", detail: "售后支持组" },
];

export const TOTAL_SCORE = EDIT_QUESTIONS.reduce((sum, q) => sum + q.score, 0);
