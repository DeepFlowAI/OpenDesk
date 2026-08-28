import type { ReactNode } from "react";
import { ExamsAdminEmptyScreen, ExamsAdminScreen } from "./screens/admin";
import {
  DeleteExamDialogScreen,
  ExamEditBasicScreen,
  ExamEditQuestionsScreen,
  ExamMembersScreen,
  QuestionEditorDialogScreen,
} from "./screens/edit";
import { MyExamsEmptyScreen, MyExamsScreen } from "./screens/my";
import { ExamResultScreen } from "./screens/result";
import {
  ExamTakingScreen,
  StartExamDialogScreen,
  SubmitExamDialogScreen,
} from "./screens/taking";

interface PrototypeScreen {
  id: string;
  title: string;
  description: string;
  render: () => ReactNode;
}

function Frame({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div className="prototype-frame relative">
      {children}
      <div className="pointer-events-none absolute bottom-4 left-4 z-50 rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">
        {id} · 1440×900
      </div>
    </div>
  );
}

export const LearningExamsScreens: PrototypeScreen[] = [
  {
    id: "learning/exams-my",
    title: "我的考试 · 卡片列表",
    description: "最高分、通过状态、剩余次数、限时信息；开始 / 再考 / 查看成绩按钮。",
    render: () => (
      <Frame id="learning/exams-my">
        <MyExamsScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exams-my-empty",
    title: "我的考试 · 空状态",
    description: "无指派考试时的空状态文案。",
    render: () => (
      <Frame id="learning/exams-my-empty">
        <MyExamsEmptyScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-start-confirm",
    title: "我的考试 · 开始确认",
    description: "有时限时提示倒计时将开始；确认后进入答题。",
    render: () => (
      <Frame id="learning/exam-start-confirm">
        <StartExamDialogScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-taking",
    title: "答题页 · 整卷作答",
    description: "倒计时、已答题数、单选/多选/判断整卷纵向；底部固定交卷栏。",
    render: () => (
      <Frame id="learning/exam-taking">
        <ExamTakingScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-submit-confirm",
    title: "答题页 · 交卷确认",
    description: "存在未作答题时的二次确认文案。",
    render: () => (
      <Frame id="learning/exam-submit-confirm">
        <SubmitExamDialogScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-result",
    title: "成绩页 · 摘要与逐题回顾",
    description: "得分/及格、历史次数、逐题对错与正确答案标记。",
    render: () => (
      <Frame id="learning/exam-result">
        <ExamResultScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exams-admin",
    title: "考试管理 · 列表",
    description: "题量、总分、及格线、参考/及格人数；已上架删除禁用。",
    render: () => (
      <Frame id="learning/exams-admin">
        <ExamsAdminScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exams-admin-empty",
    title: "考试管理 · 空状态",
    description: "无考试时空状态，主操作为新建考试。",
    render: () => (
      <Frame id="learning/exams-admin-empty">
        <ExamsAdminEmptyScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-edit-basic",
    title: "考试编辑 · 基本信息",
    description: "及格线、时限、允许次数、题目乱序等规则表单。",
    render: () => (
      <Frame id="learning/exam-edit-basic">
        <ExamEditBasicScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-edit-questions",
    title: "考试编辑 · 题目列表",
    description: "题型标签、分值、拖拽排序手柄、总分汇总。",
    render: () => (
      <Frame id="learning/exam-edit-questions">
        <ExamEditQuestionsScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-question-editor",
    title: "考试编辑 · 题目编辑 Dialog",
    description: "一期采用居中 Dialog（非 Drawer）：题干、分值、选项与正确项勾选。",
    render: () => (
      <Frame id="learning/exam-question-editor">
        <QuestionEditorDialogScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-members",
    title: "考试编辑 · 参考人员",
    description: "可见范围、指派标签、成绩表（最高分/通过状态/次数）。",
    render: () => (
      <Frame id="learning/exam-members">
        <ExamMembersScreen />
      </Frame>
    ),
  },
  {
    id: "learning/exam-delete",
    title: "考试管理 · 删除确认",
    description: "二次确认：题目与全部作答记录一并删除。",
    render: () => (
      <Frame id="learning/exam-delete">
        <DeleteExamDialogScreen />
      </Frame>
    ),
  },
];
