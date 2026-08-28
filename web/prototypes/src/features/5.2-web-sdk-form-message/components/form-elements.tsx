import type { ReactNode } from "react";

export function FieldLabel({ children, required }: { children: ReactNode; required?: boolean }) {
  return (
    <div className="flex items-center gap-0.5 text-sm font-medium text-foreground">
      <span>{children}</span>
      {required && <span className="text-destructive">*</span>}
    </div>
  );
}

export function StaticInput({ value, placeholder }: { value?: string; placeholder?: string }) {
  return (
    <div className={`flex h-10 items-center rounded-lg border border-border bg-white px-3.5 text-sm ${value ? "text-foreground" : "text-muted-foreground"}`}>
      {value || placeholder}
    </div>
  );
}

export function StaticTextarea({ value, height = "h-20" }: { value: string; height?: string }) {
  return (
    <div className={`${height} rounded-lg border border-border bg-white px-3.5 py-2.5 text-sm leading-5 text-foreground`}>
      {value}
    </div>
  );
}

export function Segmented({ selected, options }: { selected: string; options: string[] }) {
  return (
    <div className="flex gap-2">
      {options.map((option) => (
        <div
          key={option}
          className={`rounded-lg px-5 py-2.5 text-sm font-medium ${
            option === selected ? "bg-primary text-white" : "border border-border text-muted-foreground"
          }`}
        >
          {option}
        </div>
      ))}
    </div>
  );
}

export function ChannelTabs() {
  return (
    <div className="flex rounded-lg bg-muted p-0.5">
      {[
        ["界面配置", false],
        ["服务配置", true],
        ["辅助信息区", false],
      ].map(([label, active]) => (
        <div
          key={String(label)}
          className={`flex-1 rounded-md px-3 py-2 text-center text-sm ${
            active ? "border border-border bg-white font-medium text-foreground" : "text-muted-foreground"
          }`}
        >
          {label}
        </div>
      ))}
    </div>
  );
}

export function SourceTag({ source }: { source: "系统" | "自定义" }) {
  return (
    <span className="rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
      {source}
    </span>
  );
}
