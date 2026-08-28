import {
  IconArrowLeft,
  IconArrowsMaximize,
  IconLayoutGrid,
  IconPlayerPlay,
  IconPlus,
} from "@tabler/icons-react";
import { AdminShell } from "../components/admin-shell";
import { NodeOutline, PropertyPanel } from "../components/editor-panels";
import { ScriptCanvas } from "../components/script-canvas";
import { GuidedScriptDrawer } from "../components/script-drawer";

function EditorToolbar() {
  return (
    <div className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-background px-4">
      <div className="flex items-center gap-2">
        <button className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"><IconPlus size={14} />新增节点</button>
        <button className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-xs"><IconLayoutGrid size={14} />自动整理</button>
        <button className="grid h-8 w-8 place-items-center rounded-md border border-border text-muted-foreground"><IconArrowsMaximize size={14} /></button>
      </div>
      <button className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-xs"><IconPlayerPlay size={14} />预览运行</button>
    </div>
  );
}

function TemplateHeader() {
  return (
    <>
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background px-6">
        <div className="flex items-center gap-3">
          <IconArrowLeft size={18} className="text-muted-foreground" />
          <div><h1 className="font-display text-base font-semibold">编辑模板：客户满意度回访</h1><p className="mt-0.5 text-xs text-muted-foreground">配置任务字段和客服外呼引导</p></div>
          <span className="ml-2 rounded-md bg-amber-50 px-2 py-1 text-[11px] text-amber-700">未保存</span>
        </div>
        <button className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground">保存</button>
      </div>
      <div className="flex h-12 shrink-0 items-end gap-6 border-b border-border px-6">
        {[
          ["基本信息", false],
          ["任务字段", false],
          ["外呼话术", true],
        ].map(([label, active]) => <div key={String(label)} className={`flex h-12 items-center border-b-2 text-sm ${active ? "border-primary font-semibold" : "border-transparent text-muted-foreground"}`}>{label}</div>)}
      </div>
      <div className="flex h-10 shrink-0 items-center border-b border-border bg-sky-50 px-6 text-xs text-sky-900">修改只影响之后新建的外呼任务，已创建任务继续使用原话术。</div>
    </>
  );
}

export function TemplateEditorScreen({ preview = false }: { preview?: boolean }) {
  return (
    <AdminShell>
      <div className="relative flex h-full flex-col bg-background">
        <TemplateHeader />
        <EditorToolbar />
        <div className="flex min-h-0 flex-1"><NodeOutline /><div className="min-w-0 flex-1 overflow-auto"><ScriptCanvas /></div><PropertyPanel /></div>
        {preview && <div className="absolute inset-y-0 right-0 z-20"><GuidedScriptDrawer preview /></div>}
      </div>
    </AdminShell>
  );
}
