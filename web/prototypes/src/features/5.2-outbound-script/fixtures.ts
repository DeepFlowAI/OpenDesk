export type ScriptNodeKind = "start" | "script" | "branch" | "end";

export interface ScriptNodeFixture {
  id: string;
  title: string;
  kind: ScriptNodeKind;
  caption?: string;
  position: string;
  selected?: boolean;
}

export const SCRIPT_NODES: ScriptNodeFixture[] = [
  { id: "start", title: "开始", kind: "start", position: "left-8 top-[206px]" },
  { id: "identity", title: "确认接听人身份", kind: "script", caption: "您好，请问是王女士本人吗？", position: "left-[198px] top-[184px]" },
  { id: "intent", title: "确认沟通意愿", kind: "branch", caption: "客户现在是否方便沟通？", position: "left-[396px] top-[184px]", selected: true },
  { id: "continue", title: "介绍回访目的", kind: "script", caption: "本次来电想了解您对服务的评价。", position: "left-[610px] top-[58px]" },
  { id: "callback", title: "约定回拨时间", kind: "script", caption: "请问什么时间联系您比较方便？", position: "left-[610px] top-[202px]" },
  { id: "decline", title: "礼貌结束沟通", kind: "end", caption: "感谢您的接听，祝您生活愉快。", position: "left-[610px] top-[346px]" },
  { id: "rating", title: "询问服务评价", kind: "branch", caption: "您对本次服务整体满意吗？", position: "left-[824px] top-[58px]" },
];

export const BRANCH_OPTIONS = [
  { label: "方便沟通", next: "介绍回访目的" },
  { label: "现在不方便", next: "约定回拨时间" },
  { label: "明确拒绝", next: "礼貌结束沟通" },
];

export const OUTBOUND_TARGETS = [
  { name: "王女士", phone: "138 0013 8000", task: "客户满意度回访", status: "待呼叫", active: true },
  { name: "陈先生", phone: "186 8231 1976", task: "客户满意度回访", status: "需重拨" },
  { name: "刘女士", phone: "139 6742 5208", task: "售后服务回访", status: "待呼叫" },
  { name: "周先生", phone: "177 3058 6214", task: "活动线索跟进", status: "待呼叫" },
];

export const SCRIPT_DIRECTORY = [
  { depth: 0, label: "确认接听人身份", type: "话术" },
  { depth: 1, label: "是本人", type: "分支" },
  { depth: 2, label: "确认沟通意愿", type: "情景", active: true },
  { depth: 3, label: "方便沟通", type: "分支" },
  { depth: 4, label: "介绍回访目的", type: "话术" },
  { depth: 4, label: "询问服务评价", type: "情景" },
  { depth: 3, label: "现在不方便", type: "分支" },
  { depth: 4, label: "约定回拨时间", type: "话术" },
  { depth: 3, label: "明确拒绝", type: "分支" },
  { depth: 4, label: "礼貌结束沟通", type: "结束" },
  { depth: 1, label: "非本人", type: "分支" },
  { depth: 2, label: "不透露业务信息", type: "结束" },
];
