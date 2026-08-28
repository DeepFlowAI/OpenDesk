import type { ReactNode } from "react";
import {
  IconBook2,
  IconCircleArrowDown,
  IconCircleArrowUp,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
} from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import {
  ADMIN_COURSES,
  COURSE_STATUS_LABEL,
  VISIBILITY_LABEL,
  type AdminCourse,
  type CourseStatus,
} from "../fixtures";

function statusTone(status: CourseStatus) {
  if (status === "published") return "bg-emerald-50 text-emerald-700";
  if (status === "unpublished") return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}

function CourseTable({ rows }: { rows: AdminCourse[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="overflow-x-auto">
        <div style={{ minWidth: 1100 }}>
          <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
            <div className="min-w-[220px] flex-1 text-sm font-semibold text-foreground/80">课程</div>
            <div className="w-[90px] shrink-0 text-sm font-semibold text-foreground/80">状态</div>
            <div className="w-[100px] shrink-0 text-sm font-semibold text-foreground/80">可见范围</div>
            <div className="w-[70px] shrink-0 text-sm font-semibold text-foreground/80">章节数</div>
            <div className="w-[70px] shrink-0 text-sm font-semibold text-foreground/80">材料数</div>
            <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">学员数</div>
            <div className="w-[90px] shrink-0 text-sm font-semibold text-foreground/80">已完成人数</div>
            <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">更新时间</div>
            <div className="w-[96px] shrink-0 text-sm font-semibold text-foreground/80">操作</div>
          </div>
          {rows.map((row) => (
            <div
              key={row.id}
              className="flex h-14 items-center gap-6 border-t border-border px-6"
            >
              <div className="flex min-w-[220px] flex-1 items-center gap-3">
                <span className="grid h-9 w-14 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground/50">
                  <IconBook2 size={16} />
                </span>
                <span className="truncate text-sm font-medium text-foreground" title={row.name}>
                  {row.name}
                </span>
              </div>
              <div className="flex w-[90px] shrink-0 items-center">
                <span className={`rounded-md px-2 py-1 text-[11px] ${statusTone(row.status)}`}>
                  {COURSE_STATUS_LABEL[row.status]}
                </span>
              </div>
              <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">
                {VISIBILITY_LABEL[row.visibility]}
              </div>
              <div className="w-[70px] shrink-0 text-sm text-muted-foreground">{row.sectionCount}</div>
              <div className="w-[70px] shrink-0 text-sm text-muted-foreground">{row.materialCount}</div>
              <div className="w-[80px] shrink-0 text-sm text-muted-foreground">{row.learnerText}</div>
              <div className="w-[90px] shrink-0 text-sm text-muted-foreground">{row.completedCount}</div>
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
                    title="已上架课程需先下架再删除"
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

function CoursesPage({ children }: { children: ReactNode }) {
  return (
    <LearningShell tab="admin">
      <div className="flex h-full flex-col gap-6 overflow-hidden p-8">
        <div className="flex shrink-0 items-center justify-between">
          <h1 className="text-xl font-semibold text-foreground">课程管理</h1>
          <button
            type="button"
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
          >
            <IconPlus size={18} />
            新建课程
          </button>
        </div>
        <div className="flex shrink-0 items-center gap-4">
          <div className="flex h-9 w-64 items-center gap-2 rounded-lg border border-border bg-white px-3 text-sm text-muted-foreground">
            <IconSearch size={16} />
            <span>按课程名称搜索</span>
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

export function CoursesScreen() {
  return (
    <CoursesPage>
      <CourseTable rows={ADMIN_COURSES} />
      <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
        <span>共 {ADMIN_COURSES.length} 条</span>
        <span>每页 20 条</span>
      </div>
    </CoursesPage>
  );
}

export function CoursesEmptyScreen() {
  return (
    <CoursesPage>
      <div className="flex h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-white/60">
        <p className="text-sm text-muted-foreground">暂无课程，点击右上角新建课程</p>
        <button
          type="button"
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          新建课程
        </button>
      </div>
    </CoursesPage>
  );
}
