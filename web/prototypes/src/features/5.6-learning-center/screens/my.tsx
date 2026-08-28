import type { ReactNode } from "react";
import { IconBook2, IconSearch } from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import { LEARN_STATUS_LABEL, MY_COURSES, type LearnStatus, type MyCourse } from "../fixtures";

function statusTone(status: LearnStatus) {
  if (status === "completed") return "bg-emerald-50 text-emerald-700";
  if (status === "in_progress") return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}

function actionLabel(status: LearnStatus) {
  if (status === "completed") return "重新学习";
  if (status === "in_progress") return "继续学习";
  return "开始学习";
}

function CourseCard({ course }: { course: MyCourse }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-white">
      <div className="flex h-28 items-center justify-center bg-muted text-muted-foreground/50">
        <IconBook2 size={30} stroke={1.5} />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="truncate text-sm font-semibold" title={course.name}>
            {course.name}
          </h3>
          <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ${statusTone(course.status)}`}>
            {LEARN_STATUS_LABEL[course.status]}
          </span>
        </div>
        <p className="line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">{course.intro}</p>
        <div className="mt-auto space-y-1.5">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>{course.materialCount} 个材料</span>
            <span>{course.progress}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full rounded-full ${course.progress === 100 ? "bg-emerald-500" : "bg-primary"}`}
              style={{ width: `${course.progress}%` }}
            />
          </div>
          <button
            type="button"
            className={`mt-2 h-8 w-full rounded-md text-xs font-medium ${
              course.status === "not_started"
                ? "bg-primary text-primary-foreground"
                : "border border-border bg-white text-foreground"
            }`}
          >
            {actionLabel(course.status)}
          </button>
        </div>
      </div>
    </div>
  );
}

function MyLearningPage({ children }: { children: ReactNode }) {
  return (
    <LearningShell tab="my">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between px-8 py-5">
          <h1 className="text-xl font-semibold">我的学习</h1>
          <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border bg-white px-3 text-sm text-muted-foreground">
            <IconSearch size={16} />
            <span>按课程名称搜索</span>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto px-8 pb-8">{children}</main>
      </div>
    </LearningShell>
  );
}

export function MyLearningScreen() {
  return (
    <MyLearningPage>
      <div className="grid grid-cols-4 gap-4">
        {MY_COURSES.map((course) => (
          <CourseCard key={course.id} course={course} />
        ))}
      </div>
    </MyLearningPage>
  );
}

export function MyLearningEmptyScreen() {
  return (
    <MyLearningPage>
      <div className="flex h-[420px] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-white/60">
        <p className="text-sm text-muted-foreground">暂无指派给你的课程</p>
      </div>
    </MyLearningPage>
  );
}
