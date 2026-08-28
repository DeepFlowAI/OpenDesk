import type { ReactNode } from "react";
import {
  IconArrowLeft,
  IconCircleDot,
  IconGripVertical,
  IconListCheck,
  IconPencil,
  IconPlus,
  IconSearch,
  IconToggleLeft,
  IconTrash,
  IconUser,
  IconUsers,
  IconX,
} from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import { ExamsAdminScreen } from "./admin";
import {
  ASSIGN_TARGETS,
  CANDIDATES,
  EDIT_QUESTIONS,
  EXAM_NAME,
  QUESTION_TYPE_LABEL,
  RESULT_STATUS_LABEL,
  TOTAL_SCORE,
  type AssignTarget,
  type Candidate,
  type ExamResultStatus,
  type Question,
  type QuestionType,
} from "../fixtures";

const TYPE_ICON: Record<QuestionType, typeof IconCircleDot> = {
  single: IconCircleDot,
  multiple: IconListCheck,
  judge: IconToggleLeft,
};

function resultTone(status: ExamResultStatus) {
  if (status === "passed") return "bg-emerald-50 text-emerald-700";
  if (status === "failed") return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}

type EditTab = "basic" | "questions" | "members";

const EDIT_TAB_LABEL: Record<EditTab, string> = {
  basic: "基本信息",
  questions: "题目",
  members: "参考人员",
};

function ExamEditLayout({ tab, children }: { tab: EditTab; children: ReactNode }) {
  return (
    <LearningShell tab="exams">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between px-8 pt-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground">
              <IconArrowLeft size={16} />
              <span>考试管理</span>
            </div>
            <span className="h-4 w-px shrink-0 bg-border" />
            <h1 className="truncate text-base font-semibold">编辑：{EXAM_NAME}</h1>
            <span className="shrink-0 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700">
              已上架
            </span>
          </div>
          <button
            type="button"
            className="h-9 shrink-0 rounded-md border border-amber-300 bg-white px-4 text-sm font-medium text-amber-700"
          >
            下架
          </button>
        </header>
        <nav className="flex shrink-0 items-center gap-1 border-b border-border px-8">
          {(Object.keys(EDIT_TAB_LABEL) as EditTab[]).map((key) => (
            <div
              key={key}
              className={`-mb-px flex h-11 items-center border-b-2 px-3 text-sm ${
                tab === key
                  ? "border-primary font-semibold text-foreground"
                  : "border-transparent text-muted-foreground"
              }`}
            >
              {EDIT_TAB_LABEL[key]}
            </div>
          ))}
        </nav>
        <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6">{children}</main>
      </div>
    </LearningShell>
  );
}

function FormField({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 text-sm font-medium">
        {label}
        {required ? <span className="ml-0.5 text-red-500">*</span> : null}
      </div>
      {children}
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function ExamEditBasicScreen() {
  return (
    <ExamEditLayout tab="basic">
      <div className="max-w-xl space-y-6 rounded-xl border border-border bg-white p-6">
        <FormField label="考试名称" required hint="1～50 字">
          <div className="flex h-10 items-center rounded-md border border-border bg-white px-3 text-sm">
            {EXAM_NAME}
          </div>
        </FormField>
        <FormField label="考试说明" hint="≤ 200 字">
          <div className="h-24 rounded-md border border-border bg-white px-3 py-2 text-sm text-muted-foreground">
            覆盖开场白、异议处理与结束语关键知识点，满分 100，及格 60。
          </div>
        </FormField>
        <FormField label="及格线" required hint="总分的百分比，1～100">
          <div className="flex h-10 w-40 items-center gap-2 rounded-md border border-border px-3 text-sm">
            <span>60</span>
            <span className="text-muted-foreground">%</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">当前总分 {TOTAL_SCORE}，及格分 36</p>
        </FormField>
        <FormField label="作答时限">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <span className="grid h-4 w-4 place-items-center rounded-full border border-border" />
              不限时
            </label>
            <label className="flex items-center gap-2 text-sm font-medium">
              <span className="grid h-4 w-4 place-items-center rounded-full border border-primary bg-primary">
                <span className="h-1.5 w-1.5 rounded-full bg-white" />
              </span>
              限时
            </label>
            <div className="flex h-10 w-36 items-center gap-2 rounded-md border border-border px-3 text-sm">
              <span>30</span>
              <span className="text-muted-foreground">分钟</span>
            </div>
          </div>
        </FormField>
        <FormField label="允许次数" required hint="1～10，默认 1">
          <div className="flex h-10 w-40 items-center rounded-md border border-border px-3 text-sm">
            2
          </div>
        </FormField>
        <FormField label="题目乱序">
          <label className="flex items-center gap-3 text-sm">
            <span className="relative h-5 w-9 rounded-full bg-muted">
              <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow" />
            </span>
            <span className="text-muted-foreground">关闭（每次开考题目顺序固定）</span>
          </label>
        </FormField>
        <div className="flex justify-end border-t border-border pt-4">
          <button
            type="button"
            className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
          >
            保存
          </button>
        </div>
      </div>
    </ExamEditLayout>
  );
}

function QuestionRow({ question, index }: { question: Question; index: number }) {
  const TypeIcon = TYPE_ICON[question.type];
  return (
    <div className="flex items-center gap-2.5 rounded-md border border-border bg-white px-3 py-2.5">
      <IconGripVertical size={14} className="shrink-0 text-muted-foreground/50" />
      <span className="w-6 shrink-0 text-center text-xs text-muted-foreground">{index + 1}</span>
      <TypeIcon size={15} className="shrink-0 text-muted-foreground" />
      <span className="shrink-0 rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
        {QUESTION_TYPE_LABEL[question.type]}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm" title={question.stem}>
        {question.stem}
      </span>
      <span className="shrink-0 text-xs text-muted-foreground">{question.score} 分</span>
      <div className="flex shrink-0 items-center gap-2 text-muted-foreground">
        <IconPencil size={14} />
        <IconTrash size={14} className="text-red-500" />
      </div>
    </div>
  );
}

export function ExamEditQuestionsScreen() {
  return (
    <ExamEditLayout tab="questions">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            共 {EDIT_QUESTIONS.length} 题 · 总分{" "}
            <span className="font-medium text-foreground">{TOTAL_SCORE}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 items-center gap-1 rounded-md border border-border bg-white px-3 text-sm">
              <IconPlus size={14} />
              <span>新增题目</span>
              <span className="ml-1 text-[10px] text-muted-foreground">▾</span>
            </div>
          </div>
        </div>
        <div className="space-y-2">
          {EDIT_QUESTIONS.map((question, index) => (
            <QuestionRow key={question.id} question={question} index={index} />
          ))}
        </div>
      </div>
    </ExamEditLayout>
  );
}

/** Question editor as centered Dialog (chosen over Drawer for Phase 1). */
export function QuestionEditorDialogScreen() {
  return (
    <div className="relative h-full">
      <ExamEditQuestionsScreen />
      <div className="absolute inset-0 z-10 bg-black/20" />
      <div className="absolute inset-0 z-20 flex items-center justify-center">
        <div className="flex w-[560px] max-h-[860px] flex-col rounded-xl bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="text-base font-semibold">编辑题目 · 多选题</h2>
            <IconX size={18} className="text-muted-foreground" />
          </div>
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5">
            <FormField label="题干" required hint="1～500 字">
              <div className="min-h-20 rounded-md border border-border px-3 py-2 text-sm">
                处理价格异议时，以下哪些做法是正确的？（多选）
              </div>
            </FormField>
            <FormField label="分值" required>
              <div className="flex h-10 w-28 items-center rounded-md border border-border px-3 text-sm">
                15
              </div>
            </FormField>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium">
                  选项<span className="ml-0.5 text-red-500">*</span>
                </span>
                <span className="text-xs text-muted-foreground">勾选正确项（多选至少 2 项）</span>
              </div>
              <div className="space-y-2">
                {[
                  { id: "A", text: "先共情再解释价值", correct: true },
                  { id: "B", text: "直接承诺私自降价", correct: false },
                  { id: "C", text: "提供可选方案供客户比较", correct: true },
                  { id: "D", text: "打断客户并强调公司规定", correct: false },
                ].map((opt) => (
                  <div key={opt.id} className="flex items-center gap-2">
                    <span
                      className={`grid h-4 w-4 place-items-center rounded border ${
                        opt.correct ? "border-primary bg-primary text-white" : "border-border"
                      }`}
                    >
                      {opt.correct ? <span className="text-[10px] leading-none">✓</span> : null}
                    </span>
                    <span className="w-5 text-xs text-muted-foreground">{opt.id}</span>
                    <div className="flex h-9 flex-1 items-center rounded-md border border-border px-3 text-sm">
                      {opt.text}
                    </div>
                    <IconTrash size={14} className="text-muted-foreground/50" />
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="mt-3 flex h-8 items-center gap-1 text-xs font-medium text-primary"
              >
                <IconPlus size={14} />
                添加选项
              </button>
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
            <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
              取消
            </button>
            <button
              type="button"
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              保存题目
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function VisibilityRadio({ all }: { all?: boolean }) {
  return (
    <div className="flex items-center gap-6 text-sm">
      <label className="flex items-center gap-2">
        <span
          className={`grid h-4 w-4 place-items-center rounded-full border ${
            all ? "border-primary bg-primary" : "border-border"
          }`}
        >
          {all ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
        </span>
        全员可见
      </label>
      <label className="flex items-center gap-2 font-medium">
        <span
          className={`grid h-4 w-4 place-items-center rounded-full border ${
            all ? "border-border" : "border-primary bg-primary"
          }`}
        >
          {all ? null : <span className="h-1.5 w-1.5 rounded-full bg-white" />}
        </span>
        指定学员
      </label>
    </div>
  );
}

function AssignTargetTag({ target }: { target: AssignTarget }) {
  const Icon = target.type === "group" ? IconUsers : IconUser;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2.5 py-1 text-xs">
      <Icon size={13} className={target.type === "group" ? "text-sky-600" : "text-muted-foreground"} />
      <span className="font-medium">{target.name}</span>
      <span className="text-muted-foreground">{target.detail}</span>
      <IconX size={12} className="text-muted-foreground" />
    </span>
  );
}

function CandidateTable({ rows, withSource }: { rows: Candidate[]; withSource?: boolean }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-white">
      <table className="w-full text-sm">
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">姓名</th>
            <th className="px-4 py-3 font-medium">所属组</th>
            {withSource ? <th className="px-4 py-3 font-medium">来源</th> : null}
            <th className="px-4 py-3 font-medium">最高分</th>
            <th className="px-4 py-3 font-medium">状态</th>
            <th className="px-4 py-3 font-medium">已考次数</th>
            <th className="px-4 py-3 font-medium">最近交卷时间</th>
            {withSource ? <th className="px-4 py-3 font-medium">操作</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-border">
              <td className="px-4 py-3 font-medium">{row.name}</td>
              <td className="px-4 py-3 text-muted-foreground">{row.group}</td>
              {withSource ? (
                <td className="px-4 py-3 text-xs text-muted-foreground">{row.sourceText}</td>
              ) : null}
              <td className="px-4 py-3">{row.bestScore === null ? "-" : row.bestScore}</td>
              <td className="px-4 py-3">
                <span className={`rounded-md px-2 py-0.5 text-[11px] ${resultTone(row.status)}`}>
                  {RESULT_STATUS_LABEL[row.status]}
                </span>
              </td>
              <td className="px-4 py-3">{row.attemptCount}</td>
              <td className="px-4 py-3 text-muted-foreground">{row.lastSubmitAt ?? "-"}</td>
              {withSource ? (
                <td className="px-4 py-3">
                  {row.directAssigned ? (
                    <span className="text-xs text-red-600">移除</span>
                  ) : (
                    <span className="text-xs text-muted-foreground/40">—</span>
                  )}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ExamMembersScreen() {
  return (
    <ExamEditLayout tab="members">
      <div className="space-y-4">
        <VisibilityRadio />
        <div className="rounded-lg border border-border bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-medium">指派范围</span>
            <button
              type="button"
              className="flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
            >
              <IconPlus size={14} />
              添加参考人员
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {ASSIGN_TARGETS.map((target) => (
              <AssignTargetTag key={target.id} target={target} />
            ))}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            员工组为动态指派：组内新人入组后自动可见，调离后自动失去可见。共覆盖 18 名在职员工。
          </p>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">参考人员成绩</span>
          <div className="flex h-9 w-56 items-center gap-2 rounded-md border border-border bg-white px-3 text-sm text-muted-foreground">
            <IconSearch size={16} />
            <span>按姓名搜索</span>
          </div>
        </div>
        <CandidateTable rows={CANDIDATES} withSource />
      </div>
    </ExamEditLayout>
  );
}

export function DeleteExamDialogScreen() {
  return (
    <div className="relative h-full">
      <ExamsAdminScreen />
      <div className="absolute inset-0 z-10 bg-black/20" />
      <div className="absolute inset-0 z-20 flex items-center justify-center">
        <div className="w-[440px] rounded-xl bg-white p-6 shadow-2xl">
          <h2 className="text-base font-semibold">删除考试</h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            确定删除以下考试？删除后题目与全部作答记录将一并删除，不可恢复。
          </p>
          <div className="mt-4 rounded-lg border border-border bg-muted/30 px-4 py-3">
            <div className="text-xs text-muted-foreground">考试名称</div>
            <div className="mt-1 text-sm font-medium">{EXAM_NAME}</div>
          </div>
          <div className="mt-6 flex items-center justify-end gap-2">
            <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
              取消
            </button>
            <button
              type="button"
              className="h-9 rounded-md bg-red-600 px-4 text-sm font-medium text-white"
            >
              确定删除
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
