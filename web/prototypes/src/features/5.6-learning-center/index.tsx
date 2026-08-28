import type { ReactNode } from "react";
import { CoursesEmptyScreen, CoursesScreen } from "./screens/admin";
import {
  AddMembersDialogScreen,
  AddMembersEmployeeDialogScreen,
  CourseEditBasicScreen,
  CourseEditContentScreen,
  CourseMembersAllScreen,
  CourseMembersAssignedScreen,
  DeleteCourseDialogScreen,
} from "./screens/edit";
import { MyLearningEmptyScreen, MyLearningScreen } from "./screens/my";
import { LearningNavEntryScreen } from "./screens/nav";
import {
  PlayerPdfDoneScreen,
  PlayerVideoLockedScreen,
  PlayerVideoReadyScreen,
} from "./screens/player";

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

export const LearningCenterScreens: PrototypeScreen[] = [
  {
    id: "learning/nav",
    title: "主导航 · 学习中心入口",
    description: "前台主导航末尾（设置之上）新增「学习中心」；点击打开 /learning 独立全屏页。",
    render: () => (
      <Frame id="learning/nav">
        <LearningNavEntryScreen />
      </Frame>
    ),
  },
  {
    id: "learning/my",
    title: "学习中心 · 我的学习",
    description: "独立页顶部栏（返回工作台 + Tab）；课程卡片含进度条、状态标签与学习按钮。",
    render: () => (
      <Frame id="learning/my">
        <MyLearningScreen />
      </Frame>
    ),
  },
  {
    id: "learning/my-empty",
    title: "学习中心 · 我的学习空状态",
    description: "无可见课程时的空状态文案，无主操作按钮。",
    render: () => (
      <Frame id="learning/my-empty">
        <MyLearningEmptyScreen />
      </Frame>
    ),
  },
  {
    id: "learning/player-video-ready",
    title: "学习页 · 视频（可确认完成）",
    description: "播放 ≥90% 后「确认完成」可用；章节目录含完成标记，整体进度在页头。",
    render: () => (
      <Frame id="learning/player-video-ready">
        <PlayerVideoReadyScreen />
      </Frame>
    ),
  },
  {
    id: "learning/player-video-locked",
    title: "学习页 · 视频（确认完成禁用）",
    description: "播放未达 90% 时按钮禁用并提示当前进度；仅播放达标不会自动完成。",
    render: () => (
      <Frame id="learning/player-video-locked">
        <PlayerVideoLockedScreen />
      </Frame>
    ),
  },
  {
    id: "learning/player-pdf-done",
    title: "学习页 · PDF（已完成）",
    description: "PDF 内嵌预览 + 下载原文件；材料已完成后按钮展示已完成态。",
    render: () => (
      <Frame id="learning/player-pdf-done">
        <PlayerPdfDoneScreen />
      </Frame>
    ),
  },
  {
    id: "learning/courses",
    title: "课程管理 · 列表",
    description: "状态 / 可见范围 / 学员数 / 已完成人数列；已上架课程删除入口禁用。",
    render: () => (
      <Frame id="learning/courses">
        <CoursesScreen />
      </Frame>
    ),
  },
  {
    id: "learning/courses-empty",
    title: "课程管理 · 空状态",
    description: "无课程时空状态，主操作为新建课程。",
    render: () => (
      <Frame id="learning/courses-empty">
        <CoursesEmptyScreen />
      </Frame>
    ),
  },
  {
    id: "learning/edit-basic",
    title: "课程编辑 · 基本信息",
    description: "名称 / 封面 / 简介表单；页头含状态标签与下架操作。",
    render: () => (
      <Frame id="learning/edit-basic">
        <CourseEditBasicScreen />
      </Frame>
    ),
  },
  {
    id: "learning/edit-content",
    title: "课程编辑 · 课程内容",
    description: "左章节右材料；材料行含类型图标、时长与视频转码状态（转码中 / 失败可重试）。",
    render: () => (
      <Frame id="learning/edit-content">
        <CourseEditContentScreen />
      </Frame>
    ),
  },
  {
    id: "learning/members-assigned",
    title: "课程编辑 · 学习人员（指定学员）",
    description: "可见范围单选；指派范围标签（组动态指派 + 单独员工）；学员表格含来源列，仅直接指派可移除。",
    render: () => (
      <Frame id="learning/members-assigned">
        <CourseMembersAssignedScreen />
      </Frame>
    ),
  },
  {
    id: "learning/members-all",
    title: "课程编辑 · 学习人员（全员可见）",
    description: "全员说明文案（新员工自动可见）；全员进度表格无移除操作。",
    render: () => (
      <Frame id="learning/members-all">
        <CourseMembersAllScreen />
      </Frame>
    ),
  },
  {
    id: "learning/add-members",
    title: "课程编辑 · 添加学习人员（按员工组）",
    description: "默认按员工组 Tab：组多选、在职成员数、已添加置灰；组内新人自动可见。",
    render: () => (
      <Frame id="learning/add-members">
        <AddMembersDialogScreen />
      </Frame>
    ),
  },
  {
    id: "learning/add-members-employee",
    title: "课程编辑 · 添加学习人员（按员工）",
    description: "按员工 Tab：姓名搜索 + 多选；已指派（含经组覆盖）员工置灰。",
    render: () => (
      <Frame id="learning/add-members-employee">
        <AddMembersEmployeeDialogScreen />
      </Frame>
    ),
  },
  {
    id: "learning/delete-course",
    title: "课程管理 · 删除课程确认",
    description: "二次确认弹窗：课程名单独成行，说明记录一并删除。",
    render: () => (
      <Frame id="learning/delete-course">
        <DeleteCourseDialogScreen />
      </Frame>
    ),
  },
];
