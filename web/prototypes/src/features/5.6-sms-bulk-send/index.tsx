import type { ReactNode } from "react";
import { SmsTaskCreateScreen } from "./screens/create";
import { SmsTaskDetailScreen } from "./screens/detail";
import {
  SmsTaskAddTargetScreen,
  SmsTaskImportScreen,
  SmsTaskPublishConfirmScreen,
} from "./screens/dialogs";
import { SmsTaskListEmptyScreen, SmsTaskListScreen } from "./screens/list";
import { SmsRecordsSourceScreen } from "./screens/records";

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

export const SmsBulkSendScreens: PrototypeScreen[] = [
  {
    id: "engagement/sms-tasks",
    title: "短信群发任务 · 列表",
    description: "任务列表：状态、进度条、送达率、发送时间与创建人；菜单位于自动外呼任务之后。",
    render: () => (
      <Frame id="engagement/sms-tasks">
        <SmsTaskListScreen />
      </Frame>
    ),
  },
  {
    id: "engagement/sms-tasks-empty",
    title: "短信群发任务 · 空状态",
    description: "无任务时空状态文案与「新建任务」主操作。",
    render: () => (
      <Frame id="engagement/sms-tasks-empty">
        <SmsTaskListEmptyScreen />
      </Frame>
    ),
  },
  {
    id: "engagement/sms-task-new",
    title: "新建短信群发任务",
    description: "基本信息 + 短信模板选择（变量说明与正文预览）+ 发送时间（立即 / 定时）。",
    render: () => (
      <Frame id="engagement/sms-task-new">
        <SmsTaskCreateScreen />
      </Frame>
    ),
  },
  {
    id: "engagement/sms-task-detail-targets",
    title: "任务详情 · 发送对象",
    description: "概览指标 + 发送对象表格：变量摘要、状态、失败原因；导入 / 添加 / 重发失败 / 批量删除。",
    render: () => (
      <Frame id="engagement/sms-task-detail-targets">
        <SmsTaskDetailScreen tab="targets" />
      </Frame>
    ),
  },
  {
    id: "engagement/sms-task-info",
    title: "任务详情 · 任务信息",
    description: "任务信息 Tab：基本信息、模板快照正文预览与变量映射说明。",
    render: () => (
      <Frame id="engagement/sms-task-info">
        <SmsTaskDetailScreen tab="info" />
      </Frame>
    ),
  },
  {
    id: "engagement/sms-task-import",
    title: "导入发送对象 · 变量列映射",
    description: "导入弹窗字段映射步骤：文件列映射到接收号码与模板变量，必填变量必须映射。",
    render: () => (
      <Frame id="engagement/sms-task-import">
        <SmsTaskImportScreen />
      </Frame>
    ),
  },
  {
    id: "engagement/sms-task-add-target",
    title: "添加发送对象弹窗",
    description: "单条添加：接收号码 + 模板变量表单 + 正文预览。",
    render: () => (
      <Frame id="engagement/sms-task-add-target">
        <SmsTaskAddTargetScreen />
      </Frame>
    ),
  },
  {
    id: "engagement/sms-task-publish-confirm",
    title: "发布二次确认",
    description: "发布前确认任务名称、模板、对象数与发送时间。",
    render: () => (
      <Frame id="engagement/sms-task-publish-confirm">
        <SmsTaskPublishConfirmScreen />
      </Frame>
    ),
  },
  {
    id: "records/sms-source",
    title: "服务运营 · 发送记录（来源）",
    description: "发送记录新增来源筛选与来源列：单发 / 群发任务名（可跳转任务详情）。",
    render: () => (
      <Frame id="records/sms-source">
        <SmsRecordsSourceScreen />
      </Frame>
    ),
  },
];
