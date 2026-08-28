import type { ReactNode } from "react";
import { IconClipboardList, IconSearch } from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import {
  MY_EXAMS,
  RESULT_STATUS_LABEL,
  type ExamResultStatus,
  type MyExam,
} from "../fixtures";

function statusTone(status: ExamResultStatus) {
  if (status === "passed") return "bg-emerald-50 text-emerald-700";
  if (status === "failed") return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}

function actionLabel(exam: MyExam) {
  if (exam.remainingAttempts <= 0) return "查看成绩";
  if (exam.status === "not_started") return "开始考试";
  return "再考一次";
}

function ExamCard({ exam }: { exam: MyExam }) {
  const primary = exam.remainingAttempts > 0 && exam.status === "not_started";
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-white">
      <div className="flex h-28 items-center justify-center bg-muted text-muted-foreground/50">
        <IconClipboardList size={30} stroke={1.5} />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="truncate text-sm font-semibold" title={exam.name}>
            {exam.name}
          </h3>
          <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ${statusTone(exam.status)}`}>
            {RESULT_STATUS_LABEL[exam.status]}
          </span>
        </div>
        <p className="line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">{exam.intro}</p>
        <div className="mt-auto space-y-2">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>
              最高分{" "}
              <span className="font-medium text-foreground">
                {exam.bestScore === null ? "-" : exam.bestScore}
              </span>
              /{exam.totalScore}
            </span>
            <span>
              {exam.remainingAttempts > 0
                ? `剩余 ${exam.remainingAttempts} 次`
                : "次数已用完"}
            </span>
          </div>
          {exam.timeLimitMinutes ? (
            <div className="text-[11px] text-muted-foreground">限时 {exam.timeLimitMinutes} 分钟</div>
          ) : (
            <div className="text-[11px] text-muted-foreground">不限时</div>
          )}
          <div className="flex gap-2">
            {exam.status !== "not_started" && exam.remainingAttempts > 0 ? (
              <button
                type="button"
                className="h-8 flex-1 rounded-md border border-border bg-white text-xs font-medium"
              >
                查看成绩
              </button>
            ) : null}
            <button
              type="button"
              className={`h-8 flex-1 rounded-md text-xs font-medium ${
                primary || (exam.remainingAttempts > 0 && exam.status === "not_started")
                  ? "bg-primary text-primary-foreground"
                  : exam.remainingAttempts > 0
                    ? "bg-primary text-primary-foreground"
                    : "border border-border bg-white text-foreground"
              }`}
            >
              {actionLabel(exam)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MyExamsPage({ children }: { children: ReactNode }) {
  return (
    <LearningShell tab="my-exams">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between px-8 py-5">
          <h1 className="text-xl font-semibold">我的考试</h1>
          <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border bg-white px-3 text-sm text-muted-foreground">
            <IconSearch size={16} />
            <span>按考试名称搜索</span>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto px-8 pb-8">{children}</main>
      </div>
    </LearningShell>
  );
}

export function MyExamsScreen() {
  return (
    <MyExamsPage>
      <div className="grid grid-cols-4 gap-4">
        {MY_EXAMS.map((exam) => (
          <ExamCard key={exam.id} exam={exam} />
        ))}
      </div>
    </MyExamsPage>
  );
}

export function MyExamsEmptyScreen() {
  return (
    <MyExamsPage>
      <div className="flex h-[420px] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-white/60">
        <p className="text-sm text-muted-foreground">暂无指派给你的考试</p>
      </div>
    </MyExamsPage>
  );
}
