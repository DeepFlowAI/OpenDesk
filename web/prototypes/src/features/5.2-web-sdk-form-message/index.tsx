import type { ReactNode } from "react";
import { ChannelServiceScreen } from "./screens/channel-service";
import { FieldDrawerScreen } from "./screens/field-drawer";
import { SdkFormScreen } from "./screens/sdk-form";
import { SdkSuccessScreen } from "./screens/sdk-success";
import { TicketDetailScreen } from "./screens/ticket-detail";

interface PrototypeScreen {
  id: string;
  title: string;
  description: string;
  render: () => ReactNode;
}

function Stamp({ children }: { children: ReactNode }) {
  return <div className="pointer-events-none absolute bottom-4 left-4 z-[60] rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">{children}</div>;
}

function DesktopFrame({ id, children }: { id: string; children: ReactNode }) {
  return <div className="prototype-frame relative">{children}<Stamp>{id} · 1440×900</Stamp></div>;
}

function MobileStamp() {
  return <div className="pointer-events-none absolute right-2 top-16 z-[60] rounded-md border border-border bg-background/90 px-2 py-1 font-mono text-[9px] text-muted-foreground shadow-sm">原型评审 · 390×844</div>;
}

export const WebSdkFormMessageScreens: PrototypeScreen[] = [
  {
    id: "web-sdk-form-message/channel-service-form-mode",
    title: "Web 渠道 · 表单留言配置",
    description: "基于现有渠道服务配置页的滚动位置，展示互斥留言方式、工单字段顺序/必填状态和 Web SDK 用户关联说明。",
    render: () => <DesktopFrame id="web-sdk-form-message/channel-service-form-mode"><ChannelServiceScreen /></DesktopFrame>,
  },
  {
    id: "web-sdk-form-message/channel-field-drawer",
    title: "Web 渠道 · 添加工单字段",
    description: "右侧抽屉只显示允许公开填写的工单字段；用户、组织和内部处理字段不出现。",
    render: () => <DesktopFrame id="web-sdk-form-message/channel-field-drawer"><FieldDrawerScreen /></DesktopFrame>,
  },
  {
    id: "web-sdk-form-message/sdk-form-desktop",
    title: "Web SDK · 表单留言",
    description: "沿用真实 720px 独立会话页外壳；表单态替换消息列表和 Composer，只呈现配置过的工单字段。",
    render: () => <SdkFormScreen />,
  },
  {
    id: "web-sdk-form-message/sdk-success-mobile",
    title: "Web SDK · 移动端提交成功",
    description: "390×844 移动端成功状态，停留在结果页并按渠道配置展示工单编号。",
    render: () => <div className="relative w-[390px]"><SdkSuccessScreen /><MobileStamp /></div>,
  },
  {
    id: "web-sdk-form-message/ticket-detail-snapshot",
    title: "工单详情 · 表单留言快照",
    description: "基于现有工单详情左右分栏，新增只读来源信息和工单字段提交快照，关联用户仍在基础信息区。",
    render: () => <DesktopFrame id="web-sdk-form-message/ticket-detail-snapshot"><TicketDetailScreen /></DesktopFrame>,
  },
];
