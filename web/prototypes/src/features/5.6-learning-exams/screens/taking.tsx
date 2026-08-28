import {
  IconArrowLeft,
  IconCircleCheck,
  IconCircleDot,
  IconClock,
  IconListCheck,
  IconToggleLeft,
} from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import {
  EXAM_NAME,
  QUESTION_TYPE_LABEL,
  TAKING_QUESTIONS,
  type Question,
  type QuestionType,
} from "../fixtures";

const TYPE_ICON: Record<QuestionType, typeof IconCircleDot> = {
  single: IconCircleDot,
  multiple: IconListCheck,
  judge: IconToggleLeft,
};

/** Static selected state for the taking screen review. */
const SELECTED: Record<string, string[]> = {
  "q-1": ["a"],
  "q-2": ["a"],
  "q-3": [],
  "q-4": ["a"],
};

function QuestionBlock({ question, index }: { question: Question; index: number }) {
  const TypeIcon = TYPE_ICON[question.type];
  const selected = SELECTED[question.id] ?? [];
  return (
    <div className="rounded-xl border border-border bg-white p-5">
      <div className="mb-3 flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-semibold">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              <TypeIcon size={12} />
              {QUESTION_TYPE_LABEL[question.type]}
            </span>
            <span className="text-[11px] text-muted-foreground">{question.score} 分</span>
          </div>
          <p className="text-sm font-medium leading-6">{question.stem}</p>
        </div>
      </div>
      <div className="ml-10 space-y-2">
        {question.options.map((option) => {
          const checked = selected.includes(option.id);
          const multi = question.type === "multiple";
          return (
            <div
              key={option.id}
              className={`flex items-center gap-3 rounded-md border px-3 py-2.5 text-sm ${
                checked ? "border-primary/40 bg-primary/5" : "border-border bg-white"
              }`}
            >
              <span
                className={`grid h-4 w-4 shrink-0 place-items-center border ${
                  multi ? "rounded" : "rounded-full"
                } ${checked ? "border-primary bg-primary text-white" : "border-border"}`}
              >
                {checked ? <IconCircleCheck size={11} stroke={3} /> : null}
              </span>
              <span className="text-muted-foreground">{option.id === "true" || option.id === "false" ? "" : `${option.id.toUpperCase()}. `}</span>
              <span>{option.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ExamTakingScreen() {
  const answered = Object.values(SELECTED).filter((ids) => ids.length > 0).length;
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
          <div className="flex items-center gap-4 text-sm">
            <span className="text-muted-foreground">
              已答 <span className="font-medium text-foreground">{answered}</span> / {TAKING_QUESTIONS.length}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-50 px-3 py-1.5 font-mono text-sm font-semibold text-amber-700">
              <IconClock size={16} />
              14:32
            </span>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
          <div className="mx-auto max-w-3xl space-y-4 pb-24">
            {TAKING_QUESTIONS.map((question, index) => (
              <QuestionBlock key={question.id} question={question} index={index} />
            ))}
          </div>
        </main>
        <footer className="flex shrink-0 items-center justify-between border-t border-border bg-white px-8 py-3">
          <p className="text-xs text-muted-foreground">交卷后不可修改；未作答题目将按 0 分计</p>
          <button
            type="button"
            className="h-10 rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground"
          >
            交卷
          </button>
        </footer>
      </div>
    </LearningShell>
  );
}

export function StartExamDialogScreen() {
  return (
    <div className="relative h-full">
      <LearningShell tab="my-exams">
        <div className="flex h-full flex-col overflow-hidden">
          <header className="flex shrink-0 items-center justify-between px-8 py-5">
            <h1 className="text-xl font-semibold">我的考试</h1>
          </header>
          <main className="min-h-0 flex-1 px-8 pb-8">
            <div className="grid grid-cols-4 gap-4 opacity-40">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-56 rounded-xl border border-border bg-white" />
              ))}
            </div>
          </main>
        </div>
      </LearningShell>
      <div className="absolute inset-0 z-10 bg-black/20" />
      <div className="absolute inset-0 z-20 flex items-center justify-center">
        <div className="w-[440px] rounded-xl bg-white p-6 shadow-2xl">
          <h2 className="text-base font-semibold">开始考试</h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            本场限时 30 分钟，开始后将计时，确认开始？
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
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              开始
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function SubmitExamDialogScreen() {
  return (
    <div className="relative h-full">
      <ExamTakingScreen />
      <div className="absolute inset-0 z-10 bg-black/20" />
      <div className="absolute inset-0 z-20 flex items-center justify-center">
        <div className="w-[400px] rounded-xl bg-white p-6 shadow-2xl">
          <h2 className="text-base font-semibold">确认交卷</h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            还有未作答题，确认交卷？交卷后不可修改。
          </p>
          <div className="mt-6 flex items-center justify-end gap-2">
            <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
              继续答题
            </button>
            <button
              type="button"
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              确认交卷
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
