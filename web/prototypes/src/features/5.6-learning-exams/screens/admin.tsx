import type { ReactNode } from "react";
import {
  IconCircleArrowDown,
  IconCircleArrowUp,
  IconClipboardList,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
} from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import {
  ADMIN_EXAMS,
  EXAM_STATUS_LABEL,
  VISIBILITY_LABEL,
  type AdminExam,
  type ExamStatus,
} from "../fixtures";

function statusTone(status: ExamStatus) {
  if (status === "published") return "bg-emerald-50 text-emerald-700";
  if (status === "unpublished") return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}

function ExamTable({ rows }: { rows: AdminExam[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="overflow-x-auto">
        <div style={{ minWidth: 1100 }}>
          <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
            <div className="min-w-[220px] flex-1 text-sm font-semibold text-foreground/80">考试</div>
            <div className="w-[90px] shrink-0 text-sm font-semibold text-foreground/80">状态</div>
            <div className="w-[100px] shrink-0 text-sm font-semibold text-foreground/80">可见范围</div>
            <div className="w-[70px] shrink-0 text-sm font-semibold text-foreground/80">题量</div>
            <div className="w-[70px] shrink-0 text-sm font-semibold text-foreground/80">总分</div>
            <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">及格线</div>
            <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">参考人数</div>
            <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">及格人数</div>
            <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">更新时间</div>
            <div className="w-[96px] shrink-0 text-sm font-semibold text-foreground/80">操作</div>
          </div>
          {rows.map((row) => (
            <div
              key={row.id}
              className="flex h-14 items-center gap-6 border-t border-border px-6"
            >
              <div className="flex min-w-[220px] flex-1 items-center gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground/50">
                  <IconClipboardList size={16} />
                </span>
                <span className="truncate text-sm font-medium text-foreground" title={row.name}>
                  {row.name}
                </span>
              </div>
              <div className="flex w-[90px] shrink-0 items-center">
                <span className={`rounded-md px-2 py-1 text-[11px] ${statusTone(row.status)}`}>
                  {EXAM_STATUS_LABEL[row.status]}
                </span>
              </div>
              <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">
                {VISIBILITY_LABEL[row.visibility]}
              </div>
              <div className="w-[70px] shrink-0 text-sm text-muted-foreground">{row.questionCount}</div>
              <div className="w-[70px] shrink-0 text-sm text-muted-foreground">{row.totalScore}</div>
              <div className="w-[140px] shrink-0 truncate text-sm text-muted-foreground">
                {row.passScore} 分（{row.passPercent}%）
              </div>
              <div className="w-[80px] shrink-0 text-sm text-muted-foreground">{row.learnerText}</div>
              <div className="w-[80px] shrink-0 text-sm text-muted-foreground">{row.passedCount}</div>
              <div className="w-[140px] shrink-0 truncate text-sm text-muted-foreground">
                {row.updatedAt}
              </div>
              <div className="flex w-[96px] shrink-0 items-center gap-3">
                <button
                  type="button"
                  className="text-foreground/80 transition-colors hover:text-foreground"
                  aria-label="编辑"
                >
                  <IconPencil size={18} />
                </button>
                {row.status === "published" ? (
                  <button
                    type="button"
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    aria-label="下架"
                    title="下架"
                  >
                    <IconCircleArrowDown size={18} />
                  </button>
                ) : (
                  <button
                    type="button"
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    aria-label="上架"
                    title="上架"
                  >
                    <IconCircleArrowUp size={18} />
                  </button>
                )}
                {row.status === "published" ? (
                  <button
                    type="button"
                    disabled
                    className="cursor-not-allowed text-foreground/80 opacity-40"
                    title="已上架考试需先下架再删除"
                    aria-label="删除"
                  >
                    <IconTrash size={18} />
                  </button>
                ) : (
                  <button
                    type="button"
                    className="text-foreground/80 transition-colors hover:text-destructive"
                    aria-label="删除"
                  >
                    <IconTrash size={18} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ExamsPage({ children }: { children: ReactNode }) {
  return (
    <LearningShell tab="exams">
      <div className="flex h-full flex-col gap-6 overflow-hidden p-8">
        <div className="flex shrink-0 items-center justify-between">
          <h1 className="text-xl font-semibold text-foreground">考试管理</h1>
          <button
            type="button"
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
          >
            <IconPlus size={18} />
            新建考试
          </button>
        </div>
        <div className="flex shrink-0 items-center gap-4">
          <div className="flex h-9 w-64 items-center gap-2 rounded-lg border border-border bg-white px-3 text-sm text-muted-foreground">
            <IconSearch size={16} />
            <span>按考试名称搜索</span>
          </div>
          <div className="flex h-9 w-36 items-center justify-between rounded-lg border border-border bg-white px-3 text-sm text-muted-foreground">
            <span>全部状态</span>
            <span className="text-[10px]">▾</span>
          </div>
        </div>
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </LearningShell>
  );
}

export function ExamsAdminScreen() {
  return (
    <ExamsPage>
      <ExamTable rows={ADMIN_EXAMS} />
      <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
        <span>共 {ADMIN_EXAMS.length} 条</span>
        <span>每页 20 条</span>
      </div>
    </ExamsPage>
  );
}

export function ExamsAdminEmptyScreen() {
  return (
    <ExamsPage>
      <div className="flex h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-white/60">
        <p className="text-sm text-muted-foreground">暂无考试，点击右上角新建考试</p>
        <button
          type="button"
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          新建考试
        </button>
      </div>
    </ExamsPage>
  );
}
