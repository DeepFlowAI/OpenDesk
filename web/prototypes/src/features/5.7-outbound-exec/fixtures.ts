export interface OutboundTaskFixture {
  id: number;
  name: string;
  status: "进行中" | "已暂停";
  done: number;
  total: number;
  due: string;
  overdue?: boolean;
}

export interface CallRecordFixture {
  time: string;
  result: string;
  duration: string;
  agent: string;
}

export type TargetStatus = "待呼叫" | "需重拨" | "已完成";

export interface OutboundTargetFixture {
  id: number;
  name: string | null;
  phone: string;
  status: TargetStatus;
  lastCall: string;
  followUp: string;
  callCount: number;
  records: CallRecordFixture[];
}

export interface RecentCallFixture {
  id: number;
  direction: "in" | "out";
  label: string;
  time: string;
}

export const TASKS: OutboundTaskFixture[] = [
  { id: 1, name: "双 11 客户回访", status: "进行中", done: 5, total: 50, due: "2026-08-20" },
  { id: 2, name: "新客户开发", status: "进行中", done: 12, total: 40, due: "2026-08-31" },
  { id: 3, name: "老客户维护", status: "已暂停", done: 0, total: 30, due: "2026-08-10", overdue: true },
];

export const TARGETS: OutboundTargetFixture[] = [
  {
    id: 1,
    name: "张伟",
    phone: "138****8888",
    status: "待呼叫",
    lastCall: "昨天 14:30 · 未接通 · 第 3 次呼叫",
    followUp: "今天 14:00",
    callCount: 3,
    records: [
      { time: "2026-08-16 14:30", result: "未接通", duration: "—", agent: "张琪" },
      { time: "2026-08-15 10:22", result: "已接通", duration: "02:41", agent: "张琪" },
      { time: "2026-08-14 16:05", result: "未接通", duration: "—", agent: "张琪" },
      { time: "2026-08-12 11:48", result: "已接通", duration: "05:32", agent: "李楠（代接）" },
      { time: "2026-08-11 09:15", result: "未接通", duration: "—", agent: "张琪" },
    ],
  },
  {
    id: 2,
    name: "李娜",
    phone: "139****9999",
    status: "需重拨",
    lastCall: "周一 10:12 · 已接通 · 第 1 次呼叫",
    followUp: "今天 16:00",
    callCount: 1,
    records: [{ time: "2026-08-11 10:12", result: "已接通", duration: "03:18", agent: "张琪" }],
  },
  {
    id: 3,
    name: null,
    phone: "137****7777",
    status: "待呼叫",
    lastCall: "尚未呼叫",
    followUp: "—",
    callCount: 0,
    records: [],
  },
  {
    id: 4,
    name: "陈静",
    phone: "136****6666",
    status: "已完成",
    lastCall: "8月12日 15:40 · 已接通 · 第 2 次呼叫",
    followUp: "—",
    callCount: 2,
    records: [
      { time: "2026-08-12 15:40", result: "已接通", duration: "06:05", agent: "张琪" },
      { time: "2026-08-10 11:02", result: "未接通", duration: "—", agent: "张琪" },
    ],
  },
  {
    id: 5,
    name: "刘洋",
    phone: "135****5555",
    status: "待呼叫",
    lastCall: "8月10日 09:20 · 未接通 · 第 1 次呼叫",
    followUp: "—",
    callCount: 1,
    records: [{ time: "2026-08-10 09:20", result: "未接通", duration: "—", agent: "张琪" }],
  },
];

export const RECENT_CALLS: RecentCallFixture[] = [
  { id: 1, direction: "out", label: "张伟 138****8888", time: "昨天 14:30" },
  { id: 2, direction: "in", label: "400-800-1234", time: "昨天 11:05" },
  { id: 3, direction: "out", label: "李娜 139****9999", time: "周一 10:12" },
  { id: 4, direction: "in", label: "未知号码 0755****2211", time: "周一 09:48" },
];
