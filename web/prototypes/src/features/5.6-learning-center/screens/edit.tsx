import type { ReactNode } from "react";
import {
  IconAlertCircle,
  IconArrowLeft,
  IconCheck,
  IconFileText,
  IconGripVertical,
  IconLoader2,
  IconMusic,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
  IconUpload,
  IconUser,
  IconUsers,
  IconVideo,
  IconX,
} from "@tabler/icons-react";
import { LearningShell } from "../components/learning-shell";
import { CoursesScreen } from "./admin";
import {
  ALL_EMPLOYEES_PROGRESS,
  ASSIGN_GROUP_OPTIONS,
  ASSIGN_TARGETS,
  COURSE_NAME,
  EDIT_SECTIONS,
  LEARNERS,
  LEARN_STATUS_LABEL,
  PICKER_EMPLOYEES,
  type AssignTarget,
  type LearnStatus,
  type Learner,
  type Material,
  type MaterialType,
} from "../fixtures";

const TYPE_ICON: Record<MaterialType, typeof IconVideo> = {
  video: IconVideo,
  audio: IconMusic,
  pdf: IconFileText,
};

function learnStatusTone(status: LearnStatus) {
  if (status === "completed") return "bg-emerald-50 text-emerald-700";
  if (status === "in_progress") return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}

type EditTab = "basic" | "content" | "members";

const EDIT_TAB_LABEL: Record<EditTab, string> = {
  basic: "基本信息",
  content: "课程内容",
  members: "学习人员",
};

/** Edit page frame: back link, title, status tag, publish action, three tabs. */
function CourseEditLayout({ tab, children }: { tab: EditTab; children: ReactNode }) {
  return (
    <LearningShell tab="admin">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between px-8 pt-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground">
              <IconArrowLeft size={16} />
              <span>课程管理</span>
            </div>
            <span className="h-4 w-px shrink-0 bg-border" />
            <h1 className="truncate text-base font-semibold">编辑：{COURSE_NAME}</h1>
            <span className="shrink-0 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700">已上架</span>
          </div>
          <button
            type="button"
            className="h-9 shrink-0 rounded-md border border-amber-300 bg-white px-4 text-sm font-medium text-amber-700"
          >
            下架
          </button>
        </header>
        <nav className="flex shrink-0 items-center gap-1 border-b border-border px-8">
          {(Object.keys(EDIT_TAB_LABEL) as EditTab[]).map((key) => (
            <div
              key={key}
              className={`-mb-px flex h-11 items-center border-b-2 px-3 text-sm ${
                tab === key
                  ? "border-primary font-semibold text-foreground"
                  : "border-transparent text-muted-foreground"
              }`}
            >
              {EDIT_TAB_LABEL[key]}
            </div>
          ))}
        </nav>
        <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6">{children}</main>
      </div>
    </LearningShell>
  );
}

/* ---------------------------------- basic --------------------------------- */

function FormField({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-sm font-medium">
        {label}
        {required ? <span className="ml-0.5 text-red-500">*</span> : null}
      </div>
      {children}
    </div>
  );
}

export function CourseEditBasicScreen() {
  return (
    <CourseEditLayout tab="basic">
      <div className="max-w-xl space-y-6 rounded-xl border border-border bg-white p-6">
        <FormField label="课程名称" required>
          <div className="flex h-10 items-center rounded-md border border-border bg-white px-3 text-sm">
            {COURSE_NAME}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">1～50 字</p>
        </FormField>
        <FormField label="课程封面">
          <div className="flex items-center gap-4">
            <div className="flex h-24 w-40 items-center justify-center rounded-md border border-dashed border-border bg-muted/40 text-muted-foreground">
              <IconUpload size={20} />
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              可选。jpg / png，≤ 2MB，建议 16:9。
              <br />
              无封面时展示默认占位图。
            </p>
          </div>
        </FormField>
        <FormField label="课程简介">
          <div className="h-28 rounded-md border border-border bg-white px-3 py-2 text-sm text-muted-foreground">
            覆盖开场白、异议处理与结束语三段标准话术，含通话录音示例与逐句拆解。
          </div>
          <p className="mt-1 text-xs text-muted-foreground">≤ 200 字</p>
        </FormField>
        <div className="flex justify-end border-t border-border pt-4">
          <button
            type="button"
            className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
          >
            保存
          </button>
        </div>
      </div>
    </CourseEditLayout>
  );
}

/* --------------------------------- content -------------------------------- */

function TranscodeBadge({ material }: { material: Material }) {
  if (material.type !== "video" || !material.transcode || material.transcode === "ok") return null;
  if (material.transcode === "processing") {
    return (
      <span className="flex shrink-0 items-center gap-1 rounded-md bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700">
        <IconLoader2 size={12} />
        转码中
      </span>
    );
  }
  return (
    <span className="flex shrink-0 items-center gap-1 rounded-md bg-red-50 px-2 py-0.5 text-[11px] text-red-600">
      <IconAlertCircle size={12} />
      转码失败 · 重新转码
    </span>
  );
}

function MaterialEditRow({ material }: { material: Material }) {
  const TypeIcon = TYPE_ICON[material.type];
  return (
    <div className="flex items-center gap-2.5 rounded-md border border-border bg-white px-3 py-2.5">
      <IconGripVertical size={14} className="shrink-0 text-muted-foreground/50" />
      <TypeIcon size={15} className="shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate text-sm" title={material.name}>
        {material.name}
      </span>
      {material.duration ? (
        <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{material.duration}</span>
      ) : null}
      <TranscodeBadge material={material} />
      <div className="flex shrink-0 items-center gap-2 text-muted-foreground">
        <IconPencil size={14} />
        <IconTrash size={14} className="text-red-500" />
      </div>
    </div>
  );
}

export function CourseEditContentScreen() {
  return (
    <CourseEditLayout tab="content">
      <div className="flex gap-4">
        <aside className="flex w-64 shrink-0 flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">章节</span>
            <button
              type="button"
              className="flex h-7 items-center gap-1 rounded-md border border-border bg-white px-2 text-xs text-muted-foreground"
            >
              <IconPlus size={13} />
              新增章节
            </button>
          </div>
          {EDIT_SECTIONS.map((section, index) => (
            <div
              key={section.id}
              className={`flex items-center gap-2 rounded-md border px-3 py-2.5 text-sm ${
                index === 0 ? "border-primary/40 bg-white font-medium" : "border-border bg-white/70 text-foreground/80"
              }`}
            >
              <IconGripVertical size={14} className="shrink-0 text-muted-foreground/50" />
              <span className="min-w-0 flex-1 truncate">{section.name}</span>
              <IconPencil size={13} className="shrink-0 text-muted-foreground" />
              <IconTrash size={13} className="shrink-0 text-red-500" />
            </div>
          ))}
        </aside>
        <section className="min-w-0 flex-1 rounded-xl border border-border bg-muted/20 p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-semibold">{EDIT_SECTIONS[0].name}</span>
            <button
              type="button"
              className="flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
            >
              <IconUpload size={14} />
              上传材料
            </button>
          </div>
          <div className="space-y-2">
            {EDIT_SECTIONS[0].materials.map((material) => (
              <MaterialEditRow key={material.id} material={material} />
            ))}
            {EDIT_SECTIONS[1].materials.map((material) => (
              <MaterialEditRow key={material.id} material={material} />
            ))}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            支持视频（mp4 / mov / avi / mkv / flv，≤ 1GB，经阿里云视频点播转码）、音频（mp3 / wav / aac，≤ 100MB）、PDF（≤ 50MB）。不支持 PPT / Word。
          </p>
        </section>
      </div>
    </CourseEditLayout>
  );
}

/* --------------------------------- members -------------------------------- */

function LearnerTable({ rows, withSource }: { rows: Learner[]; withSource?: boolean }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-white">
      <table className="w-full text-sm">
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">姓名</th>
            <th className="px-4 py-3 font-medium">所属组</th>
            {withSource ? <th className="px-4 py-3 font-medium">来源</th> : null}
            <th className="px-4 py-3 font-medium">学习进度</th>
            <th className="px-4 py-3 font-medium">状态</th>
            <th className="px-4 py-3 font-medium">最近学习时间</th>
            {withSource ? <th className="px-4 py-3 font-medium">操作</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-border">
              <td className="px-4 py-3 font-medium">{row.name}</td>
              <td className="px-4 py-3 text-muted-foreground">{row.group}</td>
              {withSource ? <td className="px-4 py-3 text-muted-foreground">{row.sourceText}</td> : null}
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full rounded-full ${row.progress === 100 ? "bg-emerald-500" : "bg-primary"}`}
                      style={{ width: `${row.progress}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground">{row.progress}%</span>
                </div>
              </td>
              <td className="px-4 py-3">
                <span className={`rounded-md px-2 py-1 text-[11px] ${learnStatusTone(row.status)}`}>
                  {LEARN_STATUS_LABEL[row.status]}
                </span>
              </td>
              <td className="px-4 py-3 text-muted-foreground">{row.lastLearnAt ?? "—"}</td>
              {withSource ? (
                <td className="px-4 py-3">
                  {row.directAssigned ? (
                    <span className="text-xs font-medium text-red-600">移除</span>
                  ) : (
                    <span className="text-xs text-muted-foreground/50" title="经指派组进入，需移除对应组">
                      —
                    </span>
                  )}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AssignTargetTag({ target }: { target: AssignTarget }) {
  const isGroup = target.type === "group";
  return (
    <span className="flex items-center gap-1.5 rounded-md border border-border bg-white px-2.5 py-1.5 text-xs">
      {isGroup ? (
        <IconUsers size={13} className="text-sky-600" />
      ) : (
        <IconUser size={13} className="text-muted-foreground" />
      )}
      <span className="font-medium">{target.name}</span>
      <span className="text-muted-foreground">{target.detail}</span>
      <IconX size={12} className="text-muted-foreground" />
    </span>
  );
}

function VisibilityRadio({ all }: { all?: boolean }) {
  return (
    <div className="flex items-center gap-6 rounded-lg border border-border bg-white px-4 py-3">
      <span className="text-sm font-medium">可见范围</span>
      <label className="flex items-center gap-2 text-sm">
        <span
          className={`grid h-4 w-4 place-items-center rounded-full border ${
            all ? "border-primary" : "border-border"
          }`}
        >
          {all ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
        </span>
        全员可见
      </label>
      <label className="flex items-center gap-2 text-sm">
        <span
          className={`grid h-4 w-4 place-items-center rounded-full border ${
            all ? "border-border" : "border-primary"
          }`}
        >
          {all ? null : <span className="h-2 w-2 rounded-full bg-primary" />}
        </span>
        指定学员
      </label>
    </div>
  );
}

export function CourseMembersAssignedScreen() {
  return (
    <CourseEditLayout tab="members">
      <div className="space-y-4">
        <VisibilityRadio />
        <div className="rounded-lg border border-border bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-medium">指派范围</span>
            <button
              type="button"
              className="flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
            >
              <IconPlus size={14} />
              添加学习人员
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {ASSIGN_TARGETS.map((target) => (
              <AssignTargetTag key={target.id} target={target} />
            ))}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            员工组为动态指派：组内新人入组后自动可见，调离后自动失去可见。共覆盖 {LEARNERS.length + 15} 名在职员工。
          </p>
        </div>
        <LearnerTable rows={LEARNERS} withSource />
      </div>
    </CourseEditLayout>
  );
}

export function CourseMembersAllScreen() {
  return (
    <CourseEditLayout tab="members">
      <div className="space-y-4">
        <VisibilityRadio all />
        <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
          全部在职员工可学习本课程，新员工入职后自动可见。
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">全部在职员工学习情况</span>
          <div className="flex h-9 w-56 items-center gap-2 rounded-md border border-border bg-white px-3 text-sm text-muted-foreground">
            <IconSearch size={16} />
            <span>按姓名搜索</span>
          </div>
        </div>
        <LearnerTable rows={ALL_EMPLOYEES_PROGRESS} />
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>共 52 名在职员工</span>
          <span>每页 20 条</span>
        </div>
      </div>
    </CourseEditLayout>
  );
}

/* --------------------------------- dialogs -------------------------------- */

function AddMembersDialog({ tab }: { tab: "group" | "employee" }) {
  return (
    <div className="relative h-full">
      <CourseMembersAssignedScreen />
      <div className="absolute inset-0 z-10 bg-black/20" />
      <div className="absolute inset-0 z-20 flex items-center justify-center">
        <div className="flex w-[560px] flex-col rounded-xl bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="text-base font-semibold">添加学习人员</h2>
            <IconX size={18} className="text-muted-foreground" />
          </div>
          <nav className="flex items-center gap-1 border-b border-border px-5">
            {(
              [
                { key: "group", label: "按员工组" },
                { key: "employee", label: "按员工" },
              ] as const
            ).map(({ key, label }) => (
              <div
                key={key}
                className={`-mb-px flex h-10 items-center border-b-2 px-3 text-sm ${
                  tab === key
                    ? "border-primary font-semibold text-foreground"
                    : "border-transparent text-muted-foreground"
                }`}
              >
                {label}
              </div>
            ))}
          </nav>
          {tab === "group" ? (
            <div className="max-h-72 overflow-y-auto px-2 py-2">
              {ASSIGN_GROUP_OPTIONS.map((group, index) => (
                <div key={group.id} className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm">
                  <span
                    className={`grid h-4 w-4 place-items-center rounded border ${
                      group.added
                        ? "border-border bg-muted"
                        : index === 2
                          ? "border-primary bg-primary text-white"
                          : "border-border"
                    }`}
                  >
                    {group.added ? null : index === 2 ? <IconCheck size={11} stroke={3} /> : null}
                  </span>
                  <IconUsers
                    size={15}
                    className={group.added ? "text-muted-foreground/50" : "text-sky-600"}
                  />
                  <span className={group.added ? "text-muted-foreground/60" : "font-medium"}>
                    {group.name}
                  </span>
                  <span className="text-xs text-muted-foreground">在职成员 {group.memberCount} 人</span>
                  {group.added ? (
                    <span className="ml-auto text-xs text-muted-foreground/60">已添加</span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 px-5 py-3">
                <div className="flex h-9 flex-1 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground">
                  <IconSearch size={16} />
                  <span>按员工姓名搜索</span>
                </div>
              </div>
              <div className="max-h-64 overflow-y-auto border-t border-border px-2 py-2">
                {PICKER_EMPLOYEES.map((employee, index) => (
                  <div key={employee.id} className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm">
                    <span
                      className={`grid h-4 w-4 place-items-center rounded border ${
                        employee.assigned
                          ? "border-border bg-muted"
                          : index === 3
                            ? "border-primary bg-primary text-white"
                            : "border-border"
                      }`}
                    >
                      {employee.assigned ? null : index === 3 ? <IconCheck size={11} stroke={3} /> : null}
                    </span>
                    <span className={employee.assigned ? "text-muted-foreground/60" : "font-medium"}>
                      {employee.name}
                    </span>
                    <span className="text-xs text-muted-foreground">{employee.group}</span>
                    {employee.assigned ? (
                      <span className="ml-auto text-xs text-muted-foreground/60">已指派</span>
                    ) : null}
                  </div>
                ))}
              </div>
            </>
          )}
          <div className="flex items-center justify-between border-t border-border px-5 py-4">
            <span className="text-xs text-muted-foreground">
              {tab === "group"
                ? "已选 1 个组；组为动态指派，组内新人自动可见"
                : "已选 1 人；已指派（含经组覆盖）的员工不可重复选择"}
            </span>
            <div className="flex items-center gap-2">
              <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
                取消
              </button>
              <button
                type="button"
                className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Add-learners dialog, default tab: by employee group (dynamic assignment). */
export function AddMembersDialogScreen() {
  return <AddMembersDialog tab="group" />;
}

/** Add-learners dialog, employee tab: individually assigned employees. */
export function AddMembersEmployeeDialogScreen() {
  return <AddMembersDialog tab="employee" />;
}

export function DeleteCourseDialogScreen() {
  return (
    <div className="relative h-full">
      <CoursesScreen />
      <div className="absolute inset-0 z-10 bg-black/20" />
      <div className="absolute inset-0 z-20 flex items-center justify-center">
        <div className="w-[440px] rounded-xl bg-white p-6 shadow-2xl">
          <h2 className="text-base font-semibold">删除课程</h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            确定删除以下课程？删除后课程内容与全部学习记录将一并删除，不可恢复。
          </p>
          <div className="mt-4 rounded-lg border border-border bg-muted/30 px-4 py-3">
            <div className="text-xs text-muted-foreground">课程名称</div>
            <div className="mt-1 text-sm font-medium">{COURSE_NAME}</div>
          </div>
          <div className="mt-6 flex items-center justify-end gap-2">
            <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
              取消
            </button>
            <button
              type="button"
              className="h-9 rounded-md bg-red-600 px-4 text-sm font-medium text-white"
            >
              确定删除
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
