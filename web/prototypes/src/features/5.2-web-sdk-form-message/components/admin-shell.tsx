import type { ReactNode } from "react";
import {
  IconAddressBook,
  IconBuilding,
  IconBuildingCog,
  IconGitBranch,
  IconHeadset,
  IconLayoutDashboard,
  IconListSearch,
  IconMessageCircle,
  IconMessageCircleCog,
  IconNotes,
  IconShieldCheck,
  IconSortAscending,
  IconStack2,
  IconUser,
  IconUsers,
  type Icon,
} from "@tabler/icons-react";

type NavItem = { label: string; icon: Icon; active?: boolean };
type NavGroup = { label: string; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    label: "组织架构",
    items: [
      { label: "员工管理", icon: IconUser },
      { label: "员工组管理", icon: IconUsers },
      { label: "角色管理", icon: IconShieldCheck },
      { label: "默认队列设置", icon: IconSortAscending },
    ],
  },
  {
    label: "在线客服",
    items: [
      { label: "会话设置", icon: IconMessageCircleCog },
      { label: "渠道管理", icon: IconMessageCircle, active: true },
      { label: "对话路由", icon: IconGitBranch },
      { label: "会话纪要", icon: IconNotes },
    ],
  },
  {
    label: "用户组织",
    items: [
      { label: "用户字段", icon: IconAddressBook },
      { label: "组织字段", icon: IconBuilding },
      { label: "用户视图", icon: IconListSearch },
      { label: "组织设置", icon: IconBuildingCog },
    ],
  },
  {
    label: "工单",
    items: [
      { label: "工单表单布局", icon: IconLayoutDashboard },
      { label: "共享字段池", icon: IconStack2 },
      { label: "工单视图", icon: IconListSearch },
      { label: "工单流程", icon: IconGitBranch },
    ],
  },
];

function AdminSidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col gap-2 overflow-hidden border-r border-border bg-muted px-4 py-6">
      {NAV_GROUPS.map((group, groupIndex) => (
        <div key={group.label} className={`flex flex-col gap-1 ${groupIndex > 0 ? "mt-2" : ""}`}>
          <span className="mb-1 px-2.5 text-sm font-semibold text-muted-foreground">{group.label}</span>
          {group.items.map(({ label, icon: ItemIcon, active }) => (
            <div
              key={label}
              className={`flex h-9 items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm ${
                active ? "bg-white font-semibold text-foreground" : "text-foreground/80"
              }`}
            >
              <ItemIcon size={18} />
              <span>{label}</span>
            </div>
          ))}
        </div>
      ))}
    </aside>
  );
}

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full flex-col bg-white">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div className="flex items-center gap-3">
          <IconHeadset size={28} />
          <span className="text-lg font-semibold">OpenDesk 管理后台</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">姚</div>
          <span>管理员</span>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <AdminSidebar />
        <main className="min-w-0 flex-1 overflow-hidden bg-white">{children}</main>
      </div>
    </div>
  );
}
