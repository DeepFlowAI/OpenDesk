import {
  IconArrowLeft,
  IconCheck,
  IconCircleDot,
  IconListCheck,
  IconToggleLeft,
  IconX,
} from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import {
  ATTEMPT_HISTORY,
  EXAM_NAME,
  QUESTION_TYPE_LABEL,
  REVIEW_QUESTIONS,
  type QuestionType,
  type ReviewQuestion,
} from "../fixtures";

const TYPE_ICON: Record<QuestionType, typeof IconCircleDot> = {
  single: IconCircleDot,
  multiple: IconListCheck,
  judge: IconToggleLeft,
};

function ReviewBlock({ question, index }: { question: ReviewQuestion; index: number }) {
  const TypeIcon = TYPE_ICON[question.type];
  const correct = question.earned === question.score;
  return (
    <div className="rounded-xl border border-border bg-white p-5">
      <div className="mb-3 flex items-start gap-3">
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold ${
            correct ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"
          }`}
        >
          {correct ? <IconCheck size={14} /> : <IconX size={14} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">第 {index + 1} 题</span>
            <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              <TypeIcon size={12} />
              {QUESTION_TYPE_LABEL[question.type]}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {question.earned}/{question.score} 分
            </span>
          </div>
          <p className="text-sm font-medium leading-6">{question.stem}</p>
        </div>
      </div>
      <div className="ml-10 space-y-2">
        {question.options.map((option) => {
          const selected = question.selectedIds.includes(option.id);
          const isCorrect = Boolean(option.correct);
          let tone = "border-border bg-white";
          if (isCorrect) tone = "border-emerald-300 bg-emerald-50";
          else if (selected && !isCorrect) tone = "border-red-300 bg-red-50";
          return (
            <div key={option.id} className={`flex items-center gap-3 rounded-md border px-3 py-2.5 text-sm ${tone}`}>
              <span className="min-w-0 flex-1">{option.text}</span>
              {isCorrect ? (
                <span className="shrink-0 text-[11px] text-emerald-700">正确答案</span>
              ) : null}
              {selected ? (
                <span className={`shrink-0 text-[11px] ${isCorrect ? "text-emerald-700" : "text-red-600"}`}>
                  你的作答
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ExamResultScreen() {
  const best = ATTEMPT_HISTORY[0];
  return (
    <LearningShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-border bg-white px-8 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground">
              <IconArrowLeft size={16} />
              <span>我的考试</span>
            </div>
            <span className="h-4 w-px shrink-0 bg-border" />
            <h1 className="truncate text-base font-semibold">{EXAM_NAME}</h1>
          </div>
          <button
            type="button"
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            再考一次
          </button>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
          <div className="mx-auto max-w-3xl space-y-5">
            <section className="rounded-xl border border-border bg-white p-6">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <div className="text-sm text-muted-foreground">本次得分</div>
                  <div className="mt-1 flex items-baseline gap-2">
                    <span className="font-display text-4xl font-bold tracking-tight">{best.score}</span>
                    <span className="text-muted-foreground">/ {best.totalScore}</span>
                    <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                      已通过
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    及格线 60 分（60%）· 第 {best.index} 次作答 · 用时 {best.durationText}
                  </p>
                </div>
                <div className="text-right text-xs text-muted-foreground">
                  交卷时间
                  <div className="mt-1 text-sm text-foreground">{best.submittedAt}</div>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-border bg-white p-4">
              <div className="mb-3 text-sm font-medium">历史作答</div>
              <div className="space-y-2">
                {ATTEMPT_HISTORY.map((attempt, index) => (
                  <div
                    key={attempt.id}
                    className={`flex items-center justify-between rounded-md border px-3 py-2.5 text-sm ${
                      index === 0 ? "border-primary/40 bg-primary/5" : "border-border"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-medium">第 {attempt.index} 次</span>
                      <span className="text-muted-foreground">{attempt.submittedAt}</span>
                      <span
                        className={`rounded-md px-2 py-0.5 text-[11px] ${
                          attempt.passed
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-amber-50 text-amber-700"
                        }`}
                      >
                        {attempt.passed ? "通过" : "未通过"}
                      </span>
                    </div>
                    <span className="font-medium">
                      {attempt.score}/{attempt.totalScore}
                    </span>
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-3">
              <div className="text-sm font-medium">逐题回顾</div>
              {REVIEW_QUESTIONS.map((question, index) => (
                <ReviewBlock key={question.id} question={question} index={index} />
              ))}
            </section>
          </div>
        </main>
      </div>
    </LearningShell>
  );
}
