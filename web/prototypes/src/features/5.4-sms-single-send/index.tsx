import type { ReactNode } from "react";
import {
  SmsTemplateDetailScreen,
  SmsTemplatesEmptyScreen,
  SmsTemplatesScreen,
} from "./screens/admin";
import { SmsRecordDetailScreen, SmsRecordsScreen } from "./screens/records";
import {
  SendSmsDialogScreen,
  SendSmsValidationErrorScreen,
  WorkbenchIdleScreen,
  WorkbenchOnCallScreen,
} from "./screens/workbench";

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

export const SmsSingleSendScreens: PrototypeScreen[] = [
  {
    id: "sms/templates",
    title: "短信管理 · 模板列表",
    description: "管理后台呼叫中心「短信管理」仅模板只读列表；发送记录不在此页。",
    render: () => (
      <Frame id="sms/templates">
        <SmsTemplatesScreen />
      </Frame>
    ),
  },
  {
    id: "sms/templates-empty",
    title: "短信管理 · 模板空状态",
    description: "无授权模板时的空状态文案，引导联系平台管理员。",
    render: () => (
      <Frame id="sms/templates-empty">
        <SmsTemplatesEmptyScreen />
      </Frame>
    ),
  },
  {
    id: "sms/template-detail",
    title: "短信管理 · 模板详情抽屉",
    description: "只读详情：正文与变量说明；无编辑 / 删除入口。",
    render: () => (
      <Frame id="sms/template-detail">
        <SmsTemplateDetailScreen />
      </Frame>
    ),
  },
  {
    id: "sms/records",
    title: "服务运营 · 发送记录",
    description: "前台服务运营二级导航（通话报表后）「发送记录」；完整号码与状态列表。",
    render: () => (
      <Frame id="sms/records">
        <SmsRecordsScreen />
      </Frame>
    ),
  },
  {
    id: "sms/record-detail",
    title: "服务运营 · 发送详情（失败）",
    description: "失败记录详情：完整号码、正文快照、失败原因、通道回执 ID。",
    render: () => (
      <Frame id="sms/record-detail">
        <SmsRecordDetailScreen />
      </Frame>
    ),
  },
  {
    id: "sms/workbench-idle",
    title: "工作台 · 空闲拨号发短信入口",
    description: "拨号框已填号码时，呼叫按钮旁展示短信图标按钮（无文字）。",
    render: () => (
      <Frame id="sms/workbench-idle">
        <WorkbenchIdleScreen />
      </Frame>
    ),
  },
  {
    id: "sms/workbench-on-call",
    title: "工作台 · 通话中发短信入口",
    description: "通话条协作操作组内增加短信图标按钮（无文字）。",
    render: () => (
      <Frame id="sms/workbench-on-call">
        <WorkbenchOnCallScreen />
      </Frame>
    ),
  },
  {
    id: "sms/send-dialog",
    title: "工作台 · 发送短信弹窗",
    description: "选模板、填变量、正文预览；空闲态号码可编辑。",
    render: () => (
      <Frame id="sms/send-dialog">
        <SendSmsDialogScreen phase="idle" />
      </Frame>
    ),
  },
  {
    id: "sms/send-dialog-on-call",
    title: "工作台 · 通话中发送弹窗",
    description: "接收号码只读取当前用户号码；其余同单发弹窗。",
    render: () => (
      <Frame id="sms/send-dialog-on-call">
        <SendSmsDialogScreen phase="on_call" />
      </Frame>
    ),
  },
  {
    id: "sms/send-validation",
    title: "工作台 · 发送校验错误",
    description: "必填变量未填时的行内错误与预览占位。",
    render: () => (
      <Frame id="sms/send-validation">
        <SendSmsValidationErrorScreen />
      </Frame>
    ),
  },
];
