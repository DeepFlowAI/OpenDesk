import type { ReactNode } from "react";
import {
  IconArrowLeft,
  IconCheck,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconDownload,
  IconFileText,
  IconMusic,
  IconPlayerPause,
  IconPlayerPlay,
  IconVideo,
  IconVolume,
} from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import {
  COURSE_NAME,
  COURSE_SECTIONS,
  type Material,
  type MaterialType,
} from "../fixtures";

const TYPE_ICON: Record<MaterialType, typeof IconVideo> = {
  video: IconVideo,
  audio: IconMusic,
  pdf: IconFileText,
};

const TYPE_TAG: Record<MaterialType, { label: string; className: string }> = {
  video: { label: "视频", className: "bg-sky-50 text-sky-700" },
  audio: { label: "音频", className: "bg-violet-50 text-violet-700" },
  pdf: { label: "PDF", className: "bg-orange-50 text-orange-700" },
};

function MaterialRow({ material, active }: { material: Material; active?: boolean }) {
  const TypeIcon = TYPE_ICON[material.type];
  return (
    <div
      className={`flex items-center gap-2 rounded-md px-2.5 py-2 text-xs ${
        active ? "bg-primary/8 font-medium text-foreground" : "text-foreground/80"
      }`}
    >
      <TypeIcon size={14} className="shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate" title={material.name}>
        {material.name}
      </span>
      {material.duration ? (
        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{material.duration}</span>
      ) : null}
      {material.done ? (
        <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-emerald-500 text-white">
          <IconCheck size={10} stroke={3} />
        </span>
      ) : null}
    </div>
  );
}

function ChapterCatalog({ activeMaterialId }: { activeMaterialId: string }) {
  return (
    <aside className="flex w-[300px] shrink-0 flex-col gap-1 overflow-y-auto border-r border-border bg-white px-3 py-4">
      {COURSE_SECTIONS.map((section) => (
        <div key={section.id} className="mb-2">
          <div className="flex items-center justify-between px-2.5 py-2">
            <span className="text-xs font-semibold">{section.name}</span>
            <IconChevronDown size={14} className="text-muted-foreground" />
          </div>
          <div className="flex flex-col gap-0.5">
            {section.materials.map((material) => (
              <MaterialRow
                key={material.id}
                material={material}
                active={material.id === activeMaterialId}
              />
            ))}
          </div>
        </div>
      ))}
    </aside>
  );
}

function VideoPlayer({ percent }: { percent: number }) {
  return (
    <div className="flex aspect-video w-full flex-col justify-between overflow-hidden rounded-lg bg-neutral-900 text-white">
      <div className="flex flex-1 items-center justify-center">
        <span className="grid h-16 w-16 place-items-center rounded-full bg-white/15">
          <IconPlayerPlay size={30} className="ml-1" />
        </span>
      </div>
      <div className="px-4 pb-3">
        <div className="h-1 overflow-hidden rounded-full bg-white/25">
          <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-white/80">
          <div className="flex items-center gap-3">
            <IconPlayerPause size={16} />
            <IconVolume size={16} />
            <span className="font-mono">
              {percent === 92 ? "11:07 / 12:05" : "07:30 / 12:05"}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span>1.0x</span>
            <span>清晰度 720P</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function PdfPreview() {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-muted/40">
      <div className="flex h-9 items-center justify-between border-b border-border bg-white px-4 text-xs text-muted-foreground">
        <span>常见异议应对手册.pdf</span>
        <span className="font-mono">3 / 12 页</span>
      </div>
      <div className="flex justify-center px-8 py-6">
        <div className="w-full max-w-xl rounded-sm bg-white px-10 py-8 shadow-sm">
          <div className="mx-auto mb-5 h-4 w-2/5 rounded bg-neutral-200" />
          <div className="space-y-2.5">
            {Array.from({ length: 9 }).map((_, index) => (
              <div
                key={index}
                className="h-2.5 rounded bg-neutral-100"
                style={{ width: `${92 - ((index * 7) % 30)}%` }}
              />
            ))}
          </div>
          <div className="mt-6 h-24 rounded-md bg-muted" />
        </div>
      </div>
    </div>
  );
}

type PlayerVariant = "video-ready" | "video-locked" | "pdf-done";

const VARIANT_MATERIAL: Record<PlayerVariant, { id: string; name: string; type: MaterialType }> = {
  "video-ready": { id: "m-4", name: "价格异议处理示范", type: "video" },
  "video-locked": { id: "m-4", name: "价格异议处理示范", type: "video" },
  "pdf-done": { id: "m-5", name: "常见异议应对手册", type: "pdf" },
};

function ConfirmAction({ variant }: { variant: PlayerVariant }) {
  if (variant === "pdf-done") {
    return (
      <button
        type="button"
        disabled
        className="flex h-9 cursor-not-allowed items-center gap-1.5 rounded-md bg-muted px-4 text-sm font-medium text-muted-foreground"
      >
        <IconCheck size={16} />
        已完成
      </button>
    );
  }
  if (variant === "video-locked") {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">播放进度达 90% 后可确认完成（当前 62%）</span>
        <button
          type="button"
          disabled
          className="h-9 cursor-not-allowed rounded-md bg-primary/40 px-4 text-sm font-medium text-primary-foreground"
        >
          确认完成
        </button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-emerald-600">已观看 92%，可以确认完成</span>
      <button
        type="button"
        className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
      >
        确认完成
      </button>
    </div>
  );
}

function PlayerLayout({
  variant,
  content,
}: {
  variant: PlayerVariant;
  content: ReactNode;
}) {
  const material = VARIANT_MATERIAL[variant];
  const typeTag = TYPE_TAG[material.type];
  return (
    <LearningShell>
      <div className="flex h-full flex-col overflow-hidden bg-white">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground">
              <IconArrowLeft size={16} />
              <span>我的学习</span>
            </div>
            <span className="h-4 w-px shrink-0 bg-border" />
            <h1 className="truncate text-sm font-semibold">{COURSE_NAME}</h1>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">已完成 3/8 个材料</span>
        </header>
        <div className="flex min-h-0 flex-1">
          <ChapterCatalog activeMaterialId={material.id} />
          <section className="flex min-w-0 flex-1 flex-col overflow-y-auto px-8 py-5">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="text-base font-semibold">{material.name}</h2>
              <span className={`rounded-md px-2 py-0.5 text-[11px] ${typeTag.className}`}>{typeTag.label}</span>
            </div>
            {content}
            <div className="mt-4 flex items-center justify-between">
              <div>
                {material.type === "pdf" ? (
                  <button
                    type="button"
                    className="flex h-9 items-center gap-1.5 rounded-md px-3 text-sm text-muted-foreground"
                  >
                    <IconDownload size={16} />
                    下载原文件
                  </button>
                ) : null}
              </div>
              <ConfirmAction variant={variant} />
            </div>
            <div className="mt-auto flex items-center justify-between border-t border-border pt-4">
              <button
                type="button"
                className="flex h-9 items-center gap-1 rounded-md border border-border bg-white px-3 text-sm"
              >
                <IconChevronLeft size={16} />
                上一个
              </button>
              <button
                type="button"
                className="flex h-9 items-center gap-1 rounded-md border border-border bg-white px-3 text-sm"
              >
                下一个
                <IconChevronRight size={16} />
              </button>
            </div>
          </section>
        </div>
      </div>
    </LearningShell>
  );
}

/** Video at 92%: system condition met, Confirm button enabled (dual confirmation). */
export function PlayerVideoReadyScreen() {
  return (
    <PlayerLayout variant="video-ready" content={<VideoPlayer percent={92} />} />
  );
}

/** Video at 62%: Confirm disabled with inline hint; playback alone never completes. */
export function PlayerVideoLockedScreen() {
  return (
    <PlayerLayout variant="video-locked" content={<VideoPlayer percent={62} />} />
  );
}

/** PDF material: inline preview, download action, completed state. */
export function PlayerPdfDoneScreen() {
  return (
    <PlayerLayout variant="pdf-done" content={<PdfPreview />} />
  );
}
