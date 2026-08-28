import type { ReactNode } from "react";
import {
  IconArrowLeft,
  IconCircleCheck,
  IconInfoCircle,
  IconPlayerPlay,
} from "@tabler/icons-react";
import { AdminShell } from "../components/admin-shell";
import {
  CONFIG_JSON_SAMPLE,
  REACT_CODE_SAMPLE,
  URL_VARIABLES,
  type EmbeddedPageLocation,
} from "../fixtures";

function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="text-base font-semibold text-foreground">{children}</h3>;
}

function Separator() {
  return <div className="h-px w-full bg-border" />;
}

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  return (
    <div className="text-sm font-medium text-foreground">
      {label}
      {required && <span className="ml-0.5 text-red-500">*</span>}
    </div>
  );
}

function FieldHint({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-4 text-muted-foreground">{children}</p>;
}

function TextInput({ value, mono }: { value: string; mono?: boolean }) {
  return (
    <div
      className={`flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm ${
        mono ? "font-mono text-[13px]" : ""
      }`}
    >
      {value}
    </div>
  );
}

function ToggleRow({ on, label, desc }: { on: boolean; label: string; desc?: string }) {
  return (
    <div className="flex items-start justify-between gap-6 rounded-lg border border-border bg-card p-5">
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {desc && <p className="mt-1 text-xs leading-4 text-muted-foreground">{desc}</p>}
      </div>
      <div className={`mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full px-0.5 ${on ? "justify-end bg-primary" : "bg-muted"}`}>
        <div className="h-4 w-4 rounded-full bg-white shadow" />
      </div>
    </div>
  );
}

function TypeSegmented({ value }: { value: "iframe" | "react_code" }) {
  return (
    <div className="flex w-fit rounded-lg border border-border bg-muted p-0.5">
      {(
        [
          { key: "iframe" as const, label: "iframe URL" },
          { key: "react_code" as const, label: "React 代码" },
        ] as const
      ).map((option) => (
        <div
          key={option.key}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${
            option.key === value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"
          }`}
        >
          {option.label}
        </div>
      ))}
    </div>
  );
}

function CodeEditorMock({ code }: { code: string }) {
  const lines = code.split("\n");
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-[#0D1117] font-mono text-xs leading-5 text-slate-200">
      <div className="flex">
        <div className="select-none px-3 py-3 text-right text-slate-500">
          {lines.map((_, index) => (
            <div key={index}>{index + 1}</div>
          ))}
        </div>
        <pre className="min-w-0 flex-1 overflow-x-auto px-4 py-3">{code}</pre>
      </div>
    </div>
  );
}

function VariableChips({ location }: { location: EmbeddedPageLocation }) {
  return (
    <div className="rounded-lg border border-border bg-muted/40 p-4">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-foreground/80">
        <IconInfoCircle size={14} className="text-muted-foreground" />
        可用变量
      </div>
      <div className="flex flex-wrap gap-1.5">
        {URL_VARIABLES[location].map((variable) => (
          <span
            key={variable}
            className="rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
          >
            {variable}
          </span>
        ))}
      </div>
      <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
        上下文未就绪的变量替换为空字符串；页面加载完成后可发送 ready，通过 postMessage 接收完整上下文。
      </p>
    </div>
  );
}

function EditScaffold({
  active,
  title,
  children,
}: {
  active: "conversation-settings" | "call-settings";
  title: string;
  children: ReactNode;
}) {
  return (
    <AdminShell active={active}>
      <div className="flex h-full flex-col">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
          <div className="flex items-center gap-2">
            <IconArrowLeft size={20} className="text-muted-foreground" />
            <span className="text-base font-semibold text-foreground">{title}</span>
          </div>
          <button className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground">保存</button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-8 py-5">
          <div className="flex w-[720px] flex-col gap-6 p-6">{children}</div>
        </div>
      </div>
    </AdminShell>
  );
}

function IframeFormBody({
  name,
  sortOrder,
  url,
  location,
  defaultFocus,
  defaultFocusDesc,
}: {
  name: string;
  sortOrder: string;
  url: string;
  location: EmbeddedPageLocation;
  defaultFocus: boolean;
  defaultFocusDesc: string;
}) {
  return (
    <>
      <SectionTitle>基础信息</SectionTitle>
      <div className="flex flex-col gap-2">
        <FieldLabel label="名称" required />
        <TextInput value={name} />
      </div>
      <div className="flex flex-col gap-2">
        <FieldLabel label="排序" />
        <TextInput value={sortOrder} />
        <FieldHint>同一位置内按排序值升序排列 Tab</FieldHint>
      </div>

      <Separator />

      <SectionTitle>页面来源</SectionTitle>
      <div className="flex flex-col gap-2">
        <FieldLabel label="页面类型" required />
        <TypeSegmented value="iframe" />
        <FieldHint>嵌入已有第三方页面，通过 URL 变量与 postMessage 获取上下文</FieldHint>
      </div>
      <div className="flex flex-col gap-2">
        <FieldLabel label="页面 URL" required />
        <TextInput value={url} mono />
        <FieldHint>仅支持 http / https；可使用下方变量占位符，加载前按当前上下文替换</FieldHint>
      </div>
      <VariableChips location={location} />

      <Separator />

      <SectionTitle>展示规则</SectionTitle>
      <ToggleRow on label="启用" desc="关闭后坐席工作台立即不再展示该页面" />
      <ToggleRow on={defaultFocus} label="默认聚焦" desc={defaultFocusDesc} />
    </>
  );
}

/** Chat settings · edit iframe page (会员档案). */
export function ChatEditIframeScreen() {
  return (
    <EditScaffold active="conversation-settings" title="编辑：会员档案">
      <IframeFormBody
        name="会员档案"
        sortOrder="1"
        url="https://crm.example.com/member?visitor_id={visitor_id}&conversation_id={conversation_id}"
        location="chat_auxiliary"
        defaultFocus={false}
        defaultFocusDesc="选中新会话时默认激活该页面；本位置仅一个页面可开启，开启本页将自动取消其它页面"
      />
    </EditScaffold>
  );
}

/** Chat settings · edit React code page (服务提醒). */
export function ChatEditReactScreen() {
  return (
    <EditScaffold active="conversation-settings" title="编辑：服务提醒">
      <SectionTitle>基础信息</SectionTitle>
      <div className="flex flex-col gap-2">
        <FieldLabel label="名称" required />
        <TextInput value="服务提醒" />
      </div>
      <div className="flex flex-col gap-2">
        <FieldLabel label="排序" />
        <TextInput value="2" />
        <FieldHint>同一位置内按排序值升序排列 Tab</FieldHint>
      </div>

      <Separator />

      <SectionTitle>页面来源</SectionTitle>
      <div className="flex flex-col gap-2">
        <FieldLabel label="页面类型" required />
        <TypeSegmented value="react_code" />
        <FieldHint>运行受控 React 代码，自定义能力更强，代码中可再嵌 iframe</FieldHint>
      </div>
      <div className="flex flex-col gap-2">
        <FieldLabel label="React 代码" required />
        <CodeEditorMock code={REACT_CODE_SAMPLE} />
        <FieldHint>运行时注入 context / config / api；不支持 JSX 与 window、document、fetch 等浏览器能力</FieldHint>
      </div>
      <div className="flex items-center gap-2">
        <button className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-xs">
          <IconCircleCheck size={14} />
          校验代码
        </button>
        <button className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-xs">
          <IconPlayerPlay size={14} />
          预览
        </button>
        <span className="text-[11px] text-muted-foreground">预览使用模拟会话上下文，不连接真实工作台数据</span>
      </div>

      <Separator />

      <SectionTitle>初始参数</SectionTitle>
      <div className="flex flex-col gap-2">
        <FieldLabel label="config" />
        <CodeEditorMock code={CONFIG_JSON_SAMPLE} />
        <FieldHint>作为 config props 原样传入 React 代码，可放置标题、列表、链接等业务配置</FieldHint>
      </div>

      <Separator />

      <SectionTitle>展示规则</SectionTitle>
      <ToggleRow on label="启用" desc="关闭后坐席工作台立即不再展示该页面" />
      <ToggleRow on={false} label="默认聚焦" desc="选中新会话时默认激活该页面；本位置仅一个页面可开启" />
    </EditScaffold>
  );
}

/** Call center settings · edit iframe page (订单查询). */
export function CallEditIframeScreen() {
  return (
    <EditScaffold active="call-settings" title="编辑：订单查询">
      <IframeFormBody
        name="订单查询"
        sortOrder="1"
        url="https://crm.example.com/pop?phone={customer_number}&call_id={call_record_id}"
        location="call_screen_pop"
        defaultFocus
        defaultFocusDesc="新来电 / 新外呼弹屏时默认激活该页面；本位置仅一个页面可开启，开启本页将自动取消其它页面"
      />
    </EditScaffold>
  );
}
