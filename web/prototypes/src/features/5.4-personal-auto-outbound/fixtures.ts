export type LaneStage = "empty" | "dialing" | "ringing" | "screening" | "clearing";

export type LaneSlot = {
  slot: number;
  stage: LaneStage;
  customer?: string;
  phone?: string;
  elapsed?: string;
  progress?: number;
  result?: string;
};

export const OPENING_SCRIPT =
  "您好，我是续费团队的客服小王，想和您确认一下之前咨询的事项，现在方便沟通吗？";

export const RINGING_LANES: LaneSlot[] = [
  { slot: 1, stage: "ringing", customer: "王女士", phone: "138 **** 8000", elapsed: "00:18", progress: 72 },
  { slot: 2, stage: "ringing", customer: "陈先生", phone: "186 **** 1976", elapsed: "00:14", progress: 56 },
  { slot: 3, stage: "ringing", customer: "刘女士", phone: "139 **** 5208", elapsed: "00:09", progress: 36 },
  { slot: 4, stage: "dialing", customer: "周先生", phone: "177 **** 6214", elapsed: "00:04", progress: 16 },
];

export const SCREENING_LANES: LaneSlot[] = [
  { slot: 1, stage: "screening", customer: "王女士", phone: "138 **** 8000", elapsed: "00:07", progress: 100 },
  { slot: 2, stage: "ringing", customer: "陈先生", phone: "186 **** 1976", elapsed: "00:21", progress: 84 },
  { slot: 3, stage: "ringing", customer: "刘女士", phone: "139 **** 5208", elapsed: "00:16", progress: 64 },
  { slot: 4, stage: "empty" },
];

export const CLEARING_LANES: LaneSlot[] = [
  { slot: 1, stage: "ringing", customer: "陈先生", phone: "186 **** 1976", elapsed: "00:12", progress: 48 },
  { slot: 2, stage: "ringing", customer: "刘女士", phone: "139 **** 5208", elapsed: "00:08", progress: 32 },
  { slot: 3, stage: "clearing", customer: "王女士", phone: "138 **** 8000", result: "明确拒绝" },
  { slot: 4, stage: "dialing", customer: "赵先生", phone: "135 **** 4410", elapsed: "00:02", progress: 8 },
];

export const TASK_POP_CUSTOMER = {
  name: "王女士",
  phone: "138 **** 8000",
  task: "到期续费提醒",
  lastUtterance: "你好，什么事？",
};
