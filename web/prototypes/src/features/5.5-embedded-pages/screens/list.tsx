import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { AdminShell } from "../components/admin-shell";
import { EMBEDDED_PAGES, TYPE_LABEL, type EmbeddedPageLocation } from "../fixtures";

function EmbeddedPageTable({ location }: { location: EmbeddedPageLocation }) {
  const rows = EMBEDDED_PAGES.filter((page) => page.location === location);
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">名称</th>
            <th className="px-4 py-3 font-medium">页面类型</th>
            <th className="px-4 py-3 font-medium">启用</th>
            <th className="px-4 py-3 font-medium">默认聚焦</th>
            <th className="px-4 py-3 font-medium">排序</th>
            <th className="px-4 py-3 font-medium">更新时间</th>
            <th className="w-28 px-4 py-3 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((page) => (
            <tr key={page.id} className="border-t border-border">
              <td className="px-4 py-3 font-medium">
                <span className="hover:underline">{page.name}</span>
              </td>
              <td className="px-4 py-3">
                <span
                  className={`rounded-md px-2 py-1 text-[11px] ${
                    page.type === "iframe" ? "bg-sky-50 text-sky-700" : "bg-violet-50 text-violet-700"
                  }`}
                >
                  {TYPE_LABEL[page.type]}
                </span>
              </td>
              <td className="px-4 py-3">
                <span
                  className={`rounded-md px-2 py-1 text-[11px] ${
                    page.enabled ? "bg-emerald-50 text-emerald-700" : "bg-muted text-muted-foreground"
                  }`}
                >
                  {page.enabled ? "启用" : "停用"}
                </span>
              </td>
              <td className="px-4 py-3">
                {page.defaultFocus ? (
                  <span className="rounded-md bg-amber-50 px-2 py-1 text-[11px] text-amber-700">默认聚焦</span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
              <td className="px-4 py-3 text-muted-foreground">{page.sortOrder}</td>
              <td className="px-4 py-3 text-muted-foreground">{page.updatedAt}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-3 text-muted-foreground">
                  <IconPencil size={16} />
                  <IconTrash size={16} className="text-red-500" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PriorSectionStub({ title, desc }: { title: string; desc: string }) {
  return (
    <section className="opacity-50">
      <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{desc}</p>
      <div className="mt-3 h-16 rounded-lg border border-dashed border-border bg-muted/30" />
    </section>
  );
}

/** Conversation settings page with the new auxiliary embedded pages section. */
export function ChatSettingsScreen() {
  return (
    <AdminShell active="conversation-settings">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold text-foreground">会话设置</h1>
          <p className="mt-1 text-sm text-muted-foreground">在线客服配置聚合页</p>
        </header>
        <main className="min-h-0 flex-1 space-y-8 overflow-y-auto px-6 py-5">
          <PriorSectionStub title="欢迎语" desc="按渠道配置访客端欢迎语（沿用现网）" />
          <PriorSectionStub title="满意度调查" desc="会话结束后的满意度问卷（沿用现网）" />

          <section className="border-t border-border pt-6">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">辅助区嵌入页面</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  在在线工作台辅助区知识库 Tab 后追加第三方页面，支持 iframe URL 与受控 React 代码
                </p>
              </div>
              <button className="inline-flex shrink-0 items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
                <IconPlus size={16} />
                新建嵌入页面
              </button>
            </div>
            <EmbeddedPageTable location="chat_auxiliary" />
          </section>
        </main>
      </div>
    </AdminShell>
  );
}

/** Call center settings page with the new screen-pop embedded pages section. */
export function CallSettingsScreen() {
  return (
    <AdminShell active="call-settings">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold text-foreground">呼叫中心设置</h1>
        </header>
        <main className="min-h-0 flex-1 space-y-8 overflow-y-auto px-6 py-5 pb-24">
          <PriorSectionStub title="通话转写" desc="工作台实时转写开关（沿用现网）" />
          <PriorSectionStub title="通话提示音" desc="保持 / 咨询 / 三方 / 转接提示音（沿用现网）" />

          <section className="border-t border-border pt-6">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">弹屏嵌入页面</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  在呼叫中心弹屏区左上角增加 Tab，切换系统弹屏与第三方页面；支持 iframe URL 与受控 React 代码
                </p>
              </div>
              <button className="inline-flex shrink-0 items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
                <IconPlus size={16} />
                新建嵌入页面
              </button>
            </div>
            <EmbeddedPageTable location="call_screen_pop" />
          </section>
        </main>
      </div>
    </AdminShell>
  );
}
