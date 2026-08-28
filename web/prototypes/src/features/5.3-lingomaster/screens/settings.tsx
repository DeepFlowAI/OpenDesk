import {
  IconBook2,
  IconChevronDown,
  IconGitBranch,
  IconHeadset,
  IconLanguage,
  IconMessageCircleCog,
  IconNotes,
  IconPlugConnected,
  IconRobot,
  IconSettings,
  IconUsers,
  type Icon,
} from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { DEFAULT_VISITOR_PROMPT, PROMPT_VARIABLES } from "../fixtures";

interface NavItem {
  label: string;
  icon: Icon;
  active?: boolean;
}

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "在线客服",
    items: [
      { label: "会话设置", icon: IconMessageCircleCog },
      { label: "渠道", icon: IconPlugConnected },
      { label: "会话路由", icon: IconGitBranch },
      { label: "会话纪要", icon: IconNotes },
      { label: "多语言大师", icon: IconLanguage, active: true },
    ],
  },
  {
    label: "自动化",
    items: [
      { label: "机器人", icon: IconRobot },
      { label: "知识库", icon: IconBook2 },
    ],
  },
  {
    label: "组织管理",
    items: [
      { label: "客服与分组", icon: IconUsers },
      { label: "系统设置", icon: IconSettings },
    ],
  },
];

function AdminHeader() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#E5E5E5] bg-white px-6">
      <div className="flex items-center gap-2.5">
        <IconHeadset size={28} stroke={1.8} />
        <span className="text-base font-semibold tracking-tight text-[#171717]">OpenDesk 管理后台</span>
      </div>
      <div className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-[#404040]">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#E5E7EB] text-xs font-medium">李</span>
        <span>李婷</span>
        <IconChevronDown size={15} className="text-[#737373]" />
      </div>
    </header>
  );
}

function AdminSidebar() {
  return (
    <aside className="w-60 shrink-0 overflow-y-auto bg-[#F5F5F5] px-4 py-6">
      <nav className="space-y-6">
        {NAV_GROUPS.map((group) => (
          <section key={group.label}>
            <div className="mb-2 px-3 text-xs font-medium text-[#737373]">{group.label}</div>
            <div className="space-y-1">
              {group.items.map(({ label, icon: ItemIcon, active }) => (
                <div
                  key={label}
                  className={`flex h-9 items-center gap-3 rounded-lg px-3 text-sm ${
                    active ? "bg-white font-semibold text-[#171717] shadow-sm" : "text-[#525252]"
                  }`}
                >
                  <ItemIcon size={18} stroke={1.8} />
                  <span>{label}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </nav>
    </aside>
  );
}

function EnableSection() {
  return (
    <section className="border-t border-[#E5E5E5] py-6">
      <div className="flex items-start justify-between gap-8 rounded-md bg-[#FAFAFA] px-4 py-3.5">
        <div>
          <div className="text-sm font-medium text-[#262626]">启用多语言大师</div>
          <p className="mt-1.5 max-w-2xl text-sm leading-6 text-[#737373]">
            访客消息翻译为客服语言，客服消息翻译为访客语种。客服可在单个会话中临时关闭任一方向。
          </p>
        </div>
        <Switch defaultChecked aria-label="启用多语言大师" />
      </div>
    </section>
  );
}

function VariableGuide() {
  return (
    <div className="border-b border-[#EEEEEE] pb-5">
      <div className="grid grid-cols-[max-content_1fr] items-baseline gap-x-3 gap-y-1.5 text-xs text-[#737373]">
        {PROMPT_VARIABLES.map((variable) => (
          <div key={variable.name} className="contents">
            <code className="font-mono font-medium text-[#404040]">{variable.name}</code>
            <span>
              {variable.description}
              {variable.required && <span className="ml-1 text-[#C2413B]">必填</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PromptField({
  label,
  direction,
  hint,
  value,
  error,
  bordered,
}: {
  label: string;
  direction: string;
  hint: string;
  value: string;
  error?: string;
  bordered?: boolean;
}) {
  return (
    <section className={`py-5 ${bordered ? "border-t border-[#EEEEEE]" : ""}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Label className="text-sm font-semibold text-[#171717]">{label}</Label>
            <span className="rounded bg-[#F0F0F0] px-1.5 py-0.5 text-[11px] text-[#525252]">{direction}</span>
          </div>
          <p className="mt-1.5 text-sm text-[#737373]">{hint}</p>
        </div>
        <button className="shrink-0 text-sm text-[#2563EB]">恢复默认</button>
      </div>
      <Textarea
        className={`mt-3 min-h-28 resize-none rounded-md bg-[#FAFAFA] font-mono text-[13px] leading-5 ${error ? "border-[#DC2626] focus-visible:ring-[#DC2626]/20" : ""}`}
        defaultValue={value}
        aria-invalid={!!error}
      />
      <div className="mt-2 flex min-h-5 items-center justify-between gap-4">
        <p className={`text-xs ${error ? "text-[#DC2626]" : "text-[#A3A3A3]"}`}>
          {error ?? "变量将在翻译时自动替换"}
        </p>
        <span className="text-xs text-[#A3A3A3]">{value.length} / 2000</span>
      </div>
    </section>
  );
}

function PromptSettings({ agentPrompt, agentError }: { agentPrompt: string; agentError?: string }) {
  return (
    <section className="border-t border-[#E5E5E5] py-6">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-[#171717]">翻译提示词</h2>
      </div>
      <div>
        <VariableGuide />
        <PromptField
          label="访客消息翻译提示词"
          direction="访客 → 客服"
          hint="客服工作台同时展示访客原文和中文译文，访客侧不展示内部翻译信息。"
          value={DEFAULT_VISITOR_PROMPT}
        />
        <PromptField
          bordered
          label="客服消息翻译提示词"
          direction="客服 → 访客"
          hint="翻译成功后才发送给访客；失败时阻止发送，并保留输入内容。"
          value={agentPrompt}
          error={agentError}
        />
      </div>
    </section>
  );
}

export function SettingsScreen({
  agentPrompt,
  agentError,
  saveDisabled,
}: {
  agentPrompt: string;
  agentError?: string;
  saveDisabled?: boolean;
}) {
  return (
    <div className="flex h-full flex-col bg-white">
      <AdminHeader />
      <div className="flex min-h-0 flex-1">
        <AdminSidebar />
        <main className="flex-1 overflow-y-auto bg-white p-8">
          <div className="max-w-[980px]">
            <div className="mb-6 flex items-start justify-between gap-6">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight text-[#171717]">多语言大师</h1>
                <p className="mt-1.5 text-sm text-[#737373]">配置客服会话中的双向实时翻译能力</p>
              </div>
              <Button disabled={saveDisabled} className="min-w-20">保存</Button>
            </div>
            <div className="pb-8">
              <EnableSection />
              <PromptSettings agentPrompt={agentPrompt} agentError={agentError} />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
