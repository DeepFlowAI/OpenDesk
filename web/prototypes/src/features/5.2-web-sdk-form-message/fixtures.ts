export type FormFieldFixture = {
  key: string;
  name: string;
  type: string;
  source: "系统" | "自定义";
  required: boolean;
};

export const FORM_FIELDS: FormFieldFixture[] = [
  { key: "title", name: "问题标题", type: "单行文本", source: "系统", required: true },
  { key: "description", name: "问题描述", type: "多行文本", source: "系统", required: true },
  { key: "issue_type", name: "问题类型", type: "单选", source: "自定义", required: true },
  { key: "contact_email", name: "联系邮箱", type: "邮箱", source: "自定义", required: false },
  { key: "attachments", name: "相关附件", type: "文件", source: "自定义", required: false },
];

export const AVAILABLE_FIELDS: FormFieldFixture[] = [
  { key: "priority", name: "优先级", type: "单选", source: "系统", required: false },
  { key: "product_module", name: "产品模块", type: "树形单选", source: "自定义", required: false },
  { key: "expected_date", name: "期望处理日期", type: "日期", source: "自定义", required: false },
  { key: "order_number", name: "订单编号", type: "单行文本", source: "自定义", required: false },
];

export const TICKET_NUMBER = "T202608040018";
