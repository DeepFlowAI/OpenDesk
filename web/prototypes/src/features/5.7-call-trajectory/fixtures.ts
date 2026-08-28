export interface CallRecordFixture {
  id: string
  customerNumber: string
  direction: "呼入" | "呼出"
  user: string
  serviceNumber: string
  queue: string
  agent: string
  startedAt: string
  duration: string
  result: string
}

export const CALL_RECORDS: CallRecordFixture[] = [
  {
    id: "call_01JQ8F2A9K7P",
    customerNumber: "138 **** 7621",
    direction: "呼入",
    user: "陈女士",
    serviceNumber: "400 800 1001",
    queue: "技术支持组",
    agent: "李小华",
    startedAt: "2026-08-09 09:32:04",
    duration: "08:14",
    result: "客服接通",
  },
  {
    id: "call_01JQ8CY3VFXM",
    customerNumber: "186 **** 3098",
    direction: "呼出",
    user: "周先生",
    serviceNumber: "021 6123 8800",
    queue: "售后回访组",
    agent: "王小明",
    startedAt: "2026-08-09 09:18:20",
    duration: "03:42",
    result: "客服接通",
  },
  {
    id: "call_01JQ89N5RW2H",
    customerNumber: "177 **** 4480",
    direction: "呼入",
    user: "未知用户",
    serviceNumber: "400 800 1002",
    queue: "—",
    agent: "—",
    startedAt: "2026-08-09 08:54:11",
    duration: "00:26",
    result: "机器人用户挂断",
  },
  {
    id: "call_01JQ86BDA6TT",
    customerNumber: "135 **** 0914",
    direction: "呼入",
    user: "赵女士",
    serviceNumber: "400 800 1001",
    queue: "技术支持组",
    agent: "王小明",
    startedAt: "2026-08-09 08:37:52",
    duration: "05:09",
    result: "客服接通",
  },
]

export const TECHNICAL_TRANSFER_STEPS = [
  { time: "09:35:18.420", title: "发起直接转接", detail: "王小明 → 李小华（员工）", state: "done" },
  { time: "09:35:18.691", title: "创建目标媒体腿", detail: "leg_7B4F · WebRTC", state: "done" },
  { time: "09:35:19.034", title: "转接目标开始振铃", detail: "Offer #ofr_82A1", state: "done" },
  { time: "09:35:29.883", title: "目标客服接受", detail: "振铃 10.8 秒", state: "done" },
  { time: "09:35:30.102", title: "开始桥接目标客服", detail: "customer_leg ↔ leg_7B4F", state: "done" },
  { time: "09:35:30.418", title: "媒体桥接成功", detail: "FlowKit · source event fk_90182", state: "done" },
  { time: "09:35:31.006", title: "责任客服完成移交", detail: "王小明 → 李小华", state: "success" },
] as const
