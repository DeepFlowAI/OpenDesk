export type TaskStatus = "draft" | "scheduled" | "sending" | "paused" | "completed" | "archived";
export type TargetStatus = "pending" | "sending" | "submitted" | "delivered" | "failed";

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  draft: "草稿",
  scheduled: "待发送",
  sending: "发送中",
  paused: "已暂停",
  completed: "已完成",
  archived: "已归档",
};

export const TARGET_STATUS_LABEL: Record<TargetStatus, string> = {
  pending: "待发送",
  sending: "发送中",
  submitted: "已提交",
  delivered: "送达成功",
  failed: "发送失败",
};

export interface SmsTask {
  id: string;
  name: string;
  templateName: string;
  status: TaskStatus;
  total: number;
  delivered: number;
  failed: number;
  sendTime: string;
  creator: string;
  updatedAt: string;
}

export const SMS_TASKS: SmsTask[] = [
  {
    id: "task-1",
    name: "八月套餐到期提醒",
    templateName: "预约回访提醒",
    status: "sending",
    total: 1500,
    delivered: 702,
    failed: 38,
    sendTime: "立即发送",
    creator: "李婷",
    updatedAt: "2026-08-08 10:24",
  },
  {
    id: "task-2",
    name: "新功能上线通知",
    templateName: "功能上线通知",
    status: "scheduled",
    total: 3200,
    delivered: 0,
    failed: 0,
    sendTime: "2026-08-10 09:00",
    creator: "王磊",
    updatedAt: "2026-08-07 18:02",
  },
  {
    id: "task-3",
    name: "客户满意度回访邀约",
    templateName: "满意度回访邀请",
    status: "completed",
    total: 800,
    delivered: 752,
    failed: 48,
    sendTime: "立即发送",
    creator: "李婷",
    updatedAt: "2026-08-05 21:40",
  },
  {
    id: "task-4",
    name: "活动优惠推送",
    templateName: "会员活动通知",
    status: "paused",
    total: 2000,
    delivered: 870,
    failed: 80,
    sendTime: "立即发送",
    creator: "王磊",
    updatedAt: "2026-08-06 14:11",
  },
  {
    id: "task-5",
    name: "账单异常提醒",
    templateName: "账单提醒",
    status: "draft",
    total: 0,
    delivered: 0,
    failed: 0,
    sendTime: "立即发送",
    creator: "张敏",
    updatedAt: "2026-08-08 09:40",
  },
];

export interface TaskTemplateVariable {
  key: string;
  label: string;
  required: boolean;
  maxLength: number;
}

export const TASK_TEMPLATE = {
  name: "预约回访提醒",
  signName: "深流客服",
  type: "通知",
  body: "尊敬的{name}，您预约的回访时间为{time}，如需改期请回复本短信或致电客服。",
  variables: [
    { key: "name", label: "客户姓名", required: true, maxLength: 30 },
    { key: "time", label: "预约时间", required: true, maxLength: 30 },
  ] as TaskTemplateVariable[],
};

export interface SmsTarget {
  phone: string;
  name: string;
  time: string;
  status: TargetStatus;
  failReason: string | null;
  submittedAt: string | null;
  deliveredAt: string | null;
}

export const SMS_TARGETS: SmsTarget[] = [
  { phone: "13800138000", name: "王先生", time: "8月8日 14:00", status: "delivered", failReason: null, submittedAt: "2026-08-08 10:02:11", deliveredAt: "2026-08-08 10:02:14" },
  { phone: "13967425208", name: "陈女士", time: "8月8日 15:30", status: "failed", failReason: "手机号码格式错误或为空号", submittedAt: "2026-08-08 10:02:19", deliveredAt: null },
  { phone: "18682311976", name: "周先生", time: "8月9日 10:00", status: "submitted", failReason: null, submittedAt: "2026-08-08 10:03:02", deliveredAt: null },
  { phone: "17730586214", name: "吴女士", time: "8月9日 11:30", status: "sending", failReason: null, submittedAt: null, deliveredAt: null },
  { phone: "13590227654", name: "郑先生", time: "8月9日 14:00", status: "pending", failReason: null, submittedAt: null, deliveredAt: null },
  { phone: "15811442209", name: "孙女士", time: "8月10日 09:30", status: "pending", failReason: null, submittedAt: null, deliveredAt: null },
  { phone: "13755889013", name: "钱先生", time: "8月10日 10:30", status: "delivered", failReason: null, submittedAt: "2026-08-08 10:01:48", deliveredAt: "2026-08-08 10:01:51" },
  { phone: "18922334455", name: "冯女士", time: "8月10日 16:00", status: "failed", failReason: "通道返回：签名未报备", submittedAt: "2026-08-08 10:02:56", deliveredAt: null },
];

export type RecordSource = { kind: "single" } | { kind: "bulk"; taskName: string };

export interface SmsRecordRow {
  id: string;
  phone: string;
  templateName: string;
  signName: string;
  status: Exclude<TargetStatus, "sending">;
  source: RecordSource;
  sender: string;
  callId: string | null;
  sentAt: string;
}

export const SMS_RECORD_ROWS: SmsRecordRow[] = [
  { id: "r-1", phone: "13800138000", templateName: "预约回访提醒", signName: "深流客服", status: "delivered", source: { kind: "bulk", taskName: "八月套餐到期提醒" }, sender: "李婷", callId: null, sentAt: "2026-08-08 10:02:11" },
  { id: "r-2", phone: "13967425208", templateName: "预约回访提醒", signName: "深流客服", status: "failed", source: { kind: "bulk", taskName: "八月套餐到期提醒" }, sender: "李婷", callId: null, sentAt: "2026-08-08 10:02:19" },
  { id: "r-3", phone: "18682311976", templateName: "通话跟进说明", signName: "深流客服", status: "submitted", source: { kind: "single" }, sender: "李悦", callId: null, sentAt: "2026-08-07 15:10:03" },
  { id: "r-4", phone: "13590227654", templateName: "预约回访提醒", signName: "深流客服", status: "delivered", source: { kind: "single" }, sender: "张敏", callId: "CL-20260807-0182", sentAt: "2026-08-07 16:42:18" },
  { id: "r-5", phone: "17730586214", templateName: "满意度回访邀请", signName: "深流客服", status: "delivered", source: { kind: "bulk", taskName: "客户满意度回访邀约" }, sender: "李婷", callId: null, sentAt: "2026-08-05 20:15:40" },
  { id: "r-6", phone: "15811442209", templateName: "通话跟进说明", signName: "深流客服", status: "pending", source: { kind: "single" }, sender: "周凯", callId: "CL-20260807-0190", sentAt: "2026-08-07 17:05:01" },
];
