export type TemplateType = "notify" | "promo";
export type TemplateStatus = "available" | "unavailable";
export type SendStatus = "pending" | "submitted" | "delivered" | "failed";

export interface SmsVariable {
  key: string;
  label: string;
  required: boolean;
  sample?: string;
}

export interface SmsTemplate {
  id: string;
  name: string;
  signName: string;
  type: TemplateType;
  status: TemplateStatus;
  body: string;
  variables: SmsVariable[];
  updatedAt: string;
}

export interface SmsSendRecord {
  id: string;
  phone: string;
  templateName: string;
  signName: string;
  status: SendStatus;
  agentName: string;
  callId: string | null;
  sentAt: string;
  bodySnapshot: string;
  failReason: string | null;
  bizId: string;
}

export const TYPE_LABEL: Record<TemplateType, string> = {
  notify: "通知",
  promo: "推广",
};

export const STATUS_LABEL: Record<TemplateStatus, string> = {
  available: "可用",
  unavailable: "不可用",
};

export const SEND_STATUS_LABEL: Record<SendStatus, string> = {
  pending: "发送中",
  submitted: "已提交",
  delivered: "送达成功",
  failed: "发送失败",
};

export const SMS_TEMPLATES: SmsTemplate[] = [
  {
    id: "tpl-1",
    name: "预约回访提醒",
    signName: "深流客服",
    type: "notify",
    status: "available",
    body: "尊敬的{name}，您预约的回访时间为{time}，如需改期请回复本短信或致电客服。",
    variables: [
      { key: "name", label: "客户姓名", required: true, sample: "王先生" },
      { key: "time", label: "预约时间", required: true, sample: "8月8日 14:00" },
    ],
    updatedAt: "2026-08-06 15:20",
  },
  {
    id: "tpl-2",
    name: "通话跟进说明",
    signName: "深流客服",
    type: "notify",
    status: "available",
    body: "您好，关于您咨询的{topic}，处理进度为：{progress}。如有疑问请联系坐席。",
    variables: [
      { key: "topic", label: "咨询主题", required: true, sample: "套餐变更" },
      { key: "progress", label: "处理进度", required: true, sample: "已受理，预计 1 个工作日完成" },
    ],
    updatedAt: "2026-08-05 11:08",
  },
  {
    id: "tpl-3",
    name: "满意度回访邀请",
    signName: "深流客服",
    type: "promo",
    status: "unavailable",
    body: "感谢您使用我们的服务，诚邀参与满意度调查：{link}",
    variables: [{ key: "link", label: "调查链接", required: true, sample: "https://example.com/s/abc" }],
    updatedAt: "2026-08-01 09:40",
  },
];

export const SMS_RECORDS: SmsSendRecord[] = [
  {
    id: "rec-1",
    phone: "13800138000",
    templateName: "预约回访提醒",
    signName: "深流客服",
    status: "delivered",
    agentName: "张敏",
    callId: "CL-20260807-0182",
    sentAt: "2026-08-07 16:42:18",
    bodySnapshot: "【深流客服】尊敬的王先生，您预约的回访时间为8月8日 14:00，如需改期请回复本短信或致电客服。",
    failReason: null,
    bizId: "9006197469364984401",
  },
  {
    id: "rec-2",
    phone: "18682311976",
    templateName: "通话跟进说明",
    signName: "深流客服",
    status: "submitted",
    agentName: "李悦",
    callId: null,
    sentAt: "2026-08-07 15:10:03",
    bodySnapshot: "【深流客服】您好，关于您咨询的套餐变更，处理进度为：已受理，预计 1 个工作日完成。如有疑问请联系坐席。",
    failReason: null,
    bizId: "9006197469364984402",
  },
  {
    id: "rec-3",
    phone: "13967425208",
    templateName: "预约回访提醒",
    signName: "深流客服",
    status: "failed",
    agentName: "张敏",
    callId: "CL-20260807-0156",
    sentAt: "2026-08-07 11:22:47",
    bodySnapshot: "【深流客服】尊敬的陈女士，您预约的回访时间为8月7日 16:30，如需改期请回复本短信或致电客服。",
    failReason: "手机号码格式错误或为空号",
    bizId: "9006197469364984403",
  },
  {
    id: "rec-4",
    phone: "17730586214",
    templateName: "通话跟进说明",
    signName: "深流客服",
    status: "pending",
    agentName: "周凯",
    callId: "CL-20260807-0190",
    sentAt: "2026-08-07 17:05:01",
    bodySnapshot: "【深流客服】您好，关于您咨询的账单异议，处理进度为：正在核实。如有疑问请联系坐席。",
    failReason: null,
    bizId: "—",
  },
];
