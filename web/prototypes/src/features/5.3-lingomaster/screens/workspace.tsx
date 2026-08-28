import {
  IconAddressBook,
  IconAlertTriangle,
  IconArrowsExchange2,
  IconBell,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconHeadset,
  IconHistory,
  IconLanguage,
  IconLock,
  IconMessageCircle,
  IconMessagePlus,
  IconMoodSmile,
  IconPaperclip,
  IconPhone,
  IconPhoto,
  IconPinned,
  IconSearch,
  IconSend,
  IconSettings,
  IconTicket,
  IconUserPlus,
  IconWifi,
  IconX,
  type Icon,
} from "@tabler/icons-react";
import { Switch } from "@/components/ui/switch";
import {
  DEMO_AGENT,
  DEMO_CONVERSATIONS,
  DEMO_MESSAGES,
  DEMO_VISITOR,
  FAILED_TRANSLATION_DRAFT,
  INTERFACE_LANGUAGES,
  DIRECT_SEND_DRAFT,
  type DemoMessage,
} from "../fixtures";

const RAIL_ICONS: Array<{ icon: Icon; active?: boolean }> = [
  { icon: IconMessageCircle, active: true },
  { icon: IconPhone },
  { icon: IconTicket },
  { icon: IconHistory },
  { icon: IconAddressBook },
];

function IconRail() {
  return (
    <aside className="flex w-16 shrink-0 flex-col items-center justify-between border-r border-[#E5E5E5] bg-[#F5F5F5] py-4">
      <div className="flex flex-col items-center gap-4">
        <div className="flex h-12 w-16 items-center justify-center">
          <IconHeadset size={28} className="text-[#1A1A1A]" />
        </div>
        <nav className="flex flex-col items-center gap-1">
          {RAIL_ICONS.map(({ icon: RailIcon, active }, index) => (
            <div
              key={index}
              className={`flex h-11 w-11 items-center justify-center rounded-xl ${
                active ? "bg-[#E5E5E5] text-[#1A1A1A]" : "text-[#999999]"
              }`}
            >
              <RailIcon size={22} />
            </div>
          ))}
        </nav>
      </div>
      <div className="flex h-11 w-11 items-center justify-center rounded-xl text-[#999999]">
        <IconSettings size={22} />
      </div>
    </aside>
  );
}

function WorkspaceTopBar() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-end border-b border-[#E5E5E5] bg-white px-6">
      <div className="flex items-center gap-2">
        <div className="flex h-8 items-center gap-2 rounded-lg border border-[#E5E5E5] px-2.5 text-xs text-[#525252]">
          <IconWifi size={15} className="text-[#22A06B]" />
          网络正常
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-lg text-[#737373]">
          <IconBell size={18} />
        </div>
        <div className="ml-1 flex items-center gap-2 rounded-lg px-1.5 py-1">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#E5E7EB] text-xs font-medium">李</span>
          <span className="text-sm text-[#404040]">李婷</span>
          <IconChevronDown size={14} className="text-[#737373]" />
        </div>
      </div>
    </header>
  );
}

function ConversationList() {
  return (
    <section className="flex w-[280px] shrink-0 flex-col border-r border-[#E5E5E5] bg-[#F5F5F5]">
      <div className="border-b border-[#E5E5E5] px-4 pt-4">
        <div className="flex items-center gap-5 text-sm">
          <span className="border-b-2 border-[#1A1A1A] pb-3 font-semibold text-[#1A1A1A]">我的会话</span>
          <span className="pb-3 text-[#737373]">排队中</span>
          <span className="pb-3 text-[#737373]">离线</span>
        </div>
      </div>
      <div className="px-4 pb-3 pt-3">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-[#404040]">
            <span className="h-2 w-2 rounded-full bg-[#22A06B]" />
            在线
            <IconChevronDown size={14} className="text-[#737373]" />
          </div>
          <span className="rounded-full bg-white px-2.5 py-1 text-xs text-[#737373]">接待 1 / 10</span>
        </div>
        <div className="flex h-9 items-center gap-2 rounded-lg border border-[#E0E0E0] bg-white px-3 text-sm text-[#999999]">
          <IconSearch size={16} />
          <span>搜索会话</span>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        {DEMO_CONVERSATIONS.map((item) => (
          <div
            key={item.name}
            className={`relative flex min-h-[72px] items-center gap-3 px-4 py-3 ${item.active ? "bg-white" : ""}`}
          >
            {item.active && (
              <>
                <div className="absolute inset-y-0 right-0 w-1 bg-[#22A06B]" />
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#22A06B]/30 to-transparent" />
                <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-[#22A06B]/30 to-transparent" />
              </>
            )}
            <div
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 bg-white text-base font-medium"
              style={{ borderColor: item.active ? "#22A06B" : "#E0E0E0", color: item.color }}
            >
              {item.name.slice(0, 1)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-[#262626]">{item.name}</span>
                <span className="shrink-0 text-[11px] text-[#999999]">{item.time}</span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-2">
                <span className="truncate text-xs text-[#737373]">{item.snippet}</span>
                {item.unread > 0 && (
                  <span className="flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[#E5484D] px-1 text-[10px] font-semibold text-white">
                    {item.unread}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function TranslationMark() {
  return (
    <span className="inline-flex h-4 items-center gap-0.5 rounded bg-[#E8EEF9] px-1 text-[10px] font-medium text-[#2457A6]">
      <IconLanguage size={10} />译
    </span>
  );
}

const TARGET_LANGUAGE_OPTIONS = ["English", "日本語", "Français", "Español", "Deutsch", "한국어"];

function TargetLanguageSelect({ open }: { open?: boolean }) {
  return (
    <div className="mt-2">
      <div className="mb-1.5 text-xs font-medium text-[#737373]">译文目标语种</div>
      <button
        className={`flex h-9 w-full items-center justify-between rounded-lg border px-3 text-sm ${
          open ? "border-[#8AA8D8] bg-[#EEF5FF] text-[#2457A6]" : "border-[#E0E0E0] bg-white text-[#404040]"
        }`}
      >
        <span>客服语种（当前：中文）</span>
        <IconChevronDown size={14} />
      </button>
      {open && (
        <div className="mt-1.5 rounded-lg border border-[#E0E0E0] bg-white p-1.5 shadow-sm">
          <div className="flex items-center justify-between rounded-md bg-[#EEF5FF] px-2.5 py-2 text-sm font-medium text-[#2457A6]">
            <span>客服语种（当前：中文）</span>
            <IconCheck size={15} />
          </div>
          <div className="mt-1 grid grid-cols-2 gap-1">
            {TARGET_LANGUAGE_OPTIONS.map((language) => (
              <div key={language} className="rounded-md px-2.5 py-1.5 text-sm text-[#525252]">
                {language}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function LanguagePicker({ targetPickerOpen }: { targetPickerOpen?: boolean }) {
  return (
    <div className="absolute left-0 top-9 z-50 w-[350px] rounded-xl border border-[#E5E5E5] bg-white p-2 shadow-xl">
      <div className="rounded-lg bg-[#F5F5F5] px-3 py-2.5">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-[#262626]">自动检测访客语种</span>
          <IconCheck size={16} className="text-[#22A06B]" />
        </div>
        <p className="mt-1 text-xs text-[#737373]">当前：JA · 日本語 · 由访客消息自动检测</p>
      </div>
      <div className="px-3 pb-1 pt-3 text-xs font-medium text-[#999999]">手动指定</div>
      <div className="grid grid-cols-2 gap-1 px-1">
        <div className="rounded-md bg-[#EEF5FF] px-2 py-1.5 text-sm text-[#2457A6]">JA · 日本語</div>
        {INTERFACE_LANGUAGES.slice(0, 5).map((language) => (
          <div key={language.code} className="rounded-md px-2 py-1.5 text-sm text-[#525252]">
            {language.nativeName}
          </div>
        ))}
      </div>
      <div className="my-2 h-px bg-[#E5E5E5]" />
      <div className="space-y-3 px-2 py-1">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-medium text-[#262626]">翻译访客消息</div>
            <div className="mt-0.5 text-xs text-[#999999]">客服侧同时查看原文和目标语种译文</div>
          </div>
          <Switch defaultChecked aria-label="翻译访客消息" />
        </div>
        <TargetLanguageSelect open={targetPickerOpen} />
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-medium text-[#262626]">翻译发送消息</div>
            <div className="mt-0.5 text-xs text-[#999999]">翻译成功后发送给访客</div>
          </div>
          <Switch defaultChecked aria-label="翻译发送消息" />
        </div>
      </div>
      <button className="mt-2 flex h-9 w-full items-center justify-center rounded-lg border border-[#E5E5E5] text-sm text-[#525252]">
        全部关闭
      </button>
    </div>
  );
}

function HeaderAction({ icon: ActionIcon, label, dark }: { icon: Icon; label?: string; dark?: boolean }) {
  return (
    <div className={`flex h-8 items-center justify-center gap-1.5 rounded-lg px-2.5 text-xs ${dark ? "bg-[#1A1A1A] text-white" : "bg-[#E8E8E8] text-[#525252]"}`}>
      <ActionIcon size={15} />
      {label && <span>{label}</span>}
    </div>
  );
}

function ChatHeader({ variant }: { variant: WorkspaceVariant }) {
  const pickerOpen = variant === "picker" || variant === "target-picker";
  const outgoingDisabled = variant === "outgoing-disabled";
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#E5E5E5] bg-white px-6">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="truncate text-base font-semibold text-[#1A1A1A]">{DEMO_VISITOR.name}</span>
        <span className="rounded bg-[#F0F0F0] px-1.5 py-0.5 text-[11px] text-[#737373]">Web SDK</span>
        <span className="flex items-center gap-1 text-xs text-[#22A06B]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#22A06B]" />在线
        </span>
        <div className="relative">
          <button className={`flex h-7 items-center gap-1.5 rounded-lg border px-2 text-xs font-medium ${pickerOpen ? "border-[#8AA8D8] bg-[#EEF5FF] text-[#2457A6]" : "border-[#E0E0E0] bg-white text-[#525252]"}`}>
            <IconLanguage size={14} />
            {DEMO_VISITOR.languageCode}
            <IconChevronDown size={12} />
          </button>
          {pickerOpen && <LanguagePicker targetPickerOpen={variant === "target-picker"} />}
        </div>
        {outgoingDisabled && (
          <span className="rounded-md bg-[#FFF4D6] px-2 py-1 text-[11px] font-medium text-[#8A5B00]">发送翻译已关闭</span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <HeaderAction icon={IconPinned} />
        <HeaderAction icon={IconLock} />
        <HeaderAction icon={IconTicket} label="建工单" />
        <HeaderAction icon={IconUserPlus} label="协作" />
        <HeaderAction icon={IconArrowsExchange2} label="转接" />
        <HeaderAction icon={IconX} label="结束" dark />
      </div>
    </header>
  );
}

function BilingualBubble({
  original,
  translation,
  align,
}: {
  original: string;
  translation: string;
  align: "visitor" | "agent";
}) {
  const agent = align === "agent";
  return (
    <div
      className={`max-w-[70%] overflow-hidden rounded-xl ${
        agent ? "bg-[#DBEAFE]" : "border border-[#E0E0E0] bg-[#F0F0F0]"
      }`}
    >
      <div className="flex items-start gap-2 px-3.5 py-2.5">
        <span className="w-8 shrink-0 pt-0.5 text-[11px] font-medium leading-5 text-[#737373]">原文</span>
        <div className="min-w-0 flex-1 text-sm leading-6 text-[#1A1A1A]">{original}</div>
      </div>
      <div className={`flex items-start gap-2 border-t px-3.5 py-2.5 ${agent ? "border-[#BFD5F4] bg-[#EAF3FF]" : "border-[#D8D8D8] bg-white/70"}`}>
        <span className="w-8 shrink-0 whitespace-nowrap pt-0.5 text-[11px] font-medium leading-5 text-[#2457A6]">译文</span>
        <div className="min-w-0 flex-1 text-sm leading-6 text-[#1A1A1A]">{translation}</div>
      </div>
    </div>
  );
}

function VisitorMessage({ message }: { message: DemoMessage }) {
  return (
    <div className="flex flex-col items-start">
      <div className="mb-1 flex items-center gap-2 text-[11px] text-[#999999]">
        <span>{DEMO_VISITOR.name}</span>
        <span>{message.time}</span>
        <TranslationMark />
      </div>
      <BilingualBubble original={message.original} translation={message.translation} align="visitor" />
    </div>
  );
}

function AgentMessage({ message }: { message: DemoMessage }) {
  return (
    <div className="flex flex-col items-end">
      <div className="mb-1 flex items-center gap-2 text-[11px] text-[#999999]">
        <TranslationMark />
        <span>{DEMO_AGENT.name}</span>
        <span>{message.time}</span>
      </div>
      <BilingualBubble original={message.original} translation={message.translation} align="agent" />
    </div>
  );
}

function MessageArea() {
  return (
    <div className="flex-1 space-y-5 overflow-hidden bg-[#FAFAFA] px-6 py-5">
      <div className="flex justify-center">
        <span className="rounded-full bg-[#EEEEEE] px-3 py-1 text-[11px] text-[#888888]">今天 14:32</span>
      </div>
      {DEMO_MESSAGES.map((message) =>
        message.sender === "visitor" ? (
          <VisitorMessage key={message.id} message={message} />
        ) : (
          <AgentMessage key={message.id} message={message} />
        ),
      )}
    </div>
  );
}

function Composer({ variant }: { variant: WorkspaceVariant }) {
  const outgoingDisabled = variant === "outgoing-disabled";
  const sendError = variant === "send-error";
  const draft = outgoingDisabled ? DIRECT_SEND_DRAFT : sendError ? FAILED_TRANSLATION_DRAFT : "";

  return (
    <div className="shrink-0 bg-[#FAFAFA] px-6 pb-4">
      {sendError && (
        <div className="mb-2 flex items-start gap-2 rounded-lg bg-[#FDECEC] px-3 py-2 text-xs text-[#B42318]">
          <IconAlertTriangle size={15} className="mt-px shrink-0" />
          <div>
            <div className="font-medium">翻译失败，消息未发送</div>
            <div className="mt-0.5 opacity-80">输入内容已保留，请重试；在翻译成功前不会创建消息或通知访客。</div>
          </div>
        </div>
      )}
      <div className={`rounded-2xl border bg-white shadow-sm ${sendError ? "border-[#E5484D]" : "border-[#E5E5E5]"}`}>
        <div className={`min-h-[68px] px-4 py-3 text-sm leading-6 ${draft ? "text-[#262626]" : "text-[#999999]"}`}>
          {draft || `输入消息，将翻译为${DEMO_VISITOR.languageName}后发送…`}
        </div>
        <div className="flex items-center justify-between px-3 pb-3">
          <div className="flex items-center gap-1 text-[#737373]">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg"><IconMoodSmile size={18} /></div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg"><IconPhoto size={18} /></div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg"><IconPaperclip size={18} /></div>
            {!outgoingDisabled && (
              <span className="ml-1 flex items-center gap-1 rounded-md bg-[#F0F0F0] px-2 py-1 text-[11px] text-[#666666]">
                <IconLanguage size={12} />发送时翻译为 JA
              </span>
            )}
          </div>
          <button className="flex h-8 items-center gap-1.5 rounded-full bg-[#1A1A1A] px-4 text-xs font-medium text-white">
            <IconSend size={14} />发送
          </button>
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 text-xs">
      <span className="shrink-0 text-[#999999]">{label}</span>
      <span className="text-right text-[#404040]">{value}</span>
    </div>
  );
}

function AuxiliaryPanel() {
  return (
    <aside className="flex w-[300px] shrink-0 flex-col border-l border-[#E5E5E5] bg-white">
      <div className="flex h-14 items-end gap-6 border-b border-[#E5E5E5] px-5 text-sm">
        <span className="border-b-2 border-[#1A1A1A] pb-3 font-semibold text-[#1A1A1A]">基本信息</span>
        <span className="pb-3 text-[#737373]">会话纪要</span>
        <span className="pb-3 text-[#737373]">工单</span>
      </div>
      <div className="flex-1 overflow-hidden px-5 py-4">
        <section>
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#EAF6EE] font-medium text-[#277347]">田</div>
            <div>
              <div className="text-sm font-semibold text-[#262626]">{DEMO_VISITOR.name}</div>
              <div className="mt-0.5 text-xs text-[#999999]">访客 #10842</div>
            </div>
          </div>
          <DetailRow label="渠道" value={DEMO_VISITOR.channel} />
          <DetailRow label="状态" value="在线" />
          <DetailRow label="会话语种" value="JA · 日本語" />
          <DetailRow label="语种来源" value="自动检测" />
          <DetailRow label="接待客服" value={`${DEMO_AGENT.name}（中文）`} />
        </section>
        <div className="my-4 h-px bg-[#EEEEEE]" />
        <section>
          <div className="flex items-center justify-between text-sm font-semibold text-[#262626]">
            <span>访客详情</span>
            <IconChevronRight size={16} className="text-[#999999]" />
          </div>
          <div className="mt-2">
            <DetailRow label="邮箱" value="hanako@example.jp" />
            <DetailRow label="地区" value="日本 · 东京" />
            <DetailRow label="浏览页面" value="订单详情" />
            <DetailRow label="首次访问" value="2026-07-31" />
          </div>
        </section>
        <div className="my-4 h-px bg-[#EEEEEE]" />
        <button className="flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-[#E5E5E5] text-sm text-[#525252]">
          <IconMessagePlus size={16} />添加备注
        </button>
      </div>
    </aside>
  );
}

export type WorkspaceVariant = "translated" | "picker" | "target-picker" | "outgoing-disabled" | "send-error";

export function WorkspaceScreen({ variant }: { variant: WorkspaceVariant }) {
  return (
    <div className="flex h-full bg-white">
      <IconRail />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <WorkspaceTopBar />
        <main className="flex min-h-0 flex-1">
          <ConversationList />
          <section className="flex min-w-[420px] flex-1 flex-col bg-[#FAFAFA]">
            <ChatHeader variant={variant} />
            <MessageArea />
            <Composer variant={variant} />
          </section>
          <AuxiliaryPanel />
        </main>
      </div>
    </div>
  );
}
