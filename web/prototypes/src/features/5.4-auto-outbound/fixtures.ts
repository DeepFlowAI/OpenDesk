export type TaskMode = "ivr" | "bot" | "agent";

export interface AutoTaskFixture {
  name: string;
  mode: TaskMode;
  target: string;
  status: "进行中" | "暂停" | "草稿" | "已完成";
  waitingWindow?: boolean;
  owner: string;
  done: number;
  total: number;
  connectRate: string;
  updatedAt: string;
}

export const MODE_LABEL: Record<TaskMode, string> = {
  ivr: "IVR 语音流程",
  bot: "语音机器人",
  agent: "自动转人工",
};

export const AUTO_TASKS: AutoTaskFixture[] = [
  { name: "618 活动邀约通知", mode: "ivr", target: "活动通知播报流程", status: "进行中", owner: "李婷", done: 1286, total: 2000, connectRate: "46.8%", updatedAt: "2026-08-07 14:32" },
  { name: "客户满意度回访", mode: "bot", target: "满意度回访 Agent", status: "进行中", waitingWindow: true, owner: "李婷", done: 860, total: 1500, connectRate: "52.3%", updatedAt: "2026-08-07 12:05" },
  { name: "到期续费提醒", mode: "agent", target: "续费接待队列 · 比例多外呼 2:1", status: "进行中", owner: "王浩", done: 212, total: 480, connectRate: "61.4%", updatedAt: "2026-08-07 14:58" },
  { name: "新功能上线通知", mode: "ivr", target: "功能公告播报流程", status: "暂停", owner: "李婷", done: 320, total: 900, connectRate: "38.9%", updatedAt: "2026-08-06 18:20" },
  { name: "工单关闭回访", mode: "bot", target: "工单回访 Agent", status: "草稿", owner: "王浩", done: 0, total: 0, connectRate: "—", updatedAt: "2026-08-05 09:41" },
];

export interface AutoTargetFixture {
  phone: string;
  user: string;
  level: string;
  status: "待呼叫" | "呼叫中" | "需重拨" | "已完成" | "无效号码";
  calls: number;
  connected: number;
  lastResult: string;
  retriesLeft: number;
}

export const AUTO_TARGETS: AutoTargetFixture[] = [
  { phone: "138 0013 8000", user: "王女士", level: "VIP 客户", status: "呼叫中", calls: 1, connected: 1, lastResult: "已接通", retriesLeft: 2 },
  { phone: "186 8231 1976", user: "陈先生", level: "普通客户", status: "需重拨", calls: 1, connected: 0, lastResult: "无人接听", retriesLeft: 1 },
  { phone: "139 6742 5208", user: "刘女士", level: "VIP 客户", status: "已完成", calls: 2, connected: 1, lastResult: "满意", retriesLeft: 0 },
  { phone: "177 3058 6214", user: "周先生", level: "普通客户", status: "待呼叫", calls: 0, connected: 0, lastResult: "—", retriesLeft: 2 },
  { phone: "150 9921 3345", user: "未匹配", level: "—", status: "已完成", calls: 1, connected: 1, lastResult: "无意向", retriesLeft: 0 },
  { phone: "188 4410 7762", user: "赵女士", level: "普通客户", status: "无效号码", calls: 1, connected: 0, lastResult: "空号", retriesLeft: 0 },
];

export type Disposition = "已接通" | "无人接听" | "忙线" | "关机停机" | "空号" | "呼叫失败";

export interface CallRecordFixture {
  phone: string;
  time: string;
  disposition: Disposition;
  reception: string;
  duration: string;
  result: string;
}

export const CALL_RECORDS: CallRecordFixture[] = [
  { phone: "138 0013 8000", time: "2026-08-07 14:58:12", disposition: "已接通", reception: "满意度回访 Agent", duration: "02:41", result: "意向：满意" },
  { phone: "186 8231 1976", time: "2026-08-07 14:55:03", disposition: "无人接听", reception: "未接待", duration: "—", result: "—" },
  { phone: "139 6742 5208", time: "2026-08-07 14:51:47", disposition: "已接通", reception: "满意度回访 Agent", duration: "03:05", result: "意向：一般 · 转人工" },
  { phone: "135 2210 8890", time: "2026-08-07 14:49:20", disposition: "忙线", reception: "未接待", duration: "—", result: "—" },
  { phone: "188 4410 7762", time: "2026-08-07 14:44:31", disposition: "空号", reception: "未接待", duration: "—", result: "—" },
  { phone: "150 9921 3345", time: "2026-08-07 14:40:08", disposition: "已接通", reception: "满意度回访 Agent", duration: "00:52", result: "意向：拒绝联系" },
];

export interface LiveCallFixture {
  phone: string;
  user: string;
  state: "通话中" | "振铃中" | "排队待接入";
  agent?: string;
  elapsed: string;
}

export const LIVE_CALLS: LiveCallFixture[] = [
  { phone: "138 0013 8000", user: "王女士", state: "通话中", agent: "张琪", elapsed: "01:42" },
  { phone: "136 7789 1204", user: "吴先生", state: "通话中", agent: "刘畅", elapsed: "00:58" },
  { phone: "159 3310 5527", user: "郑女士", state: "振铃中", elapsed: "00:21" },
  { phone: "187 5540 9918", user: "孙先生", state: "排队待接入", elapsed: "00:09" },
];

export const LIVE_AGENTS = [
  { name: "张琪", state: "通话中" },
  { name: "刘畅", state: "通话中" },
  { name: "陈默", state: "就绪" },
  { name: "李楠", state: "就绪" },
  { name: "赵欣", state: "话后处理" },
  { name: "周岩", state: "小休" },
] as const;

export const RETRY_POLICY_ROWS = [
  { disposition: "无人接听", retries: "2 次", interval: "120 分钟", enabled: true },
  { disposition: "忙线", retries: "2 次", interval: "30 分钟", enabled: true },
  { disposition: "关机停机", retries: "1 次", interval: "720 分钟", enabled: true },
  { disposition: "空号 / 呼叫失败", retries: "不重试", interval: "—", enabled: false },
];
