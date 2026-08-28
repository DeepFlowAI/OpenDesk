export type EmbeddedPageLocation = "chat_auxiliary" | "call_screen_pop";
export type EmbeddedPageType = "iframe" | "react_code";

export interface EmbeddedPageRow {
  id: number;
  name: string;
  location: EmbeddedPageLocation;
  type: EmbeddedPageType;
  enabled: boolean;
  defaultFocus: boolean;
  sortOrder: number;
  updatedAt: string;
}

export const LOCATION_LABEL: Record<EmbeddedPageLocation, string> = {
  chat_auxiliary: "在线工作台辅助区",
  call_screen_pop: "呼叫中心弹屏区",
};

export const TYPE_LABEL: Record<EmbeddedPageType, string> = {
  iframe: "iframe",
  react_code: "React 代码",
};

export const EMBEDDED_PAGES: EmbeddedPageRow[] = [
  {
    id: 1,
    name: "订单查询",
    location: "call_screen_pop",
    type: "iframe",
    enabled: true,
    defaultFocus: true,
    sortOrder: 1,
    updatedAt: "2026-08-05 14:32",
  },
  {
    id: 2,
    name: "物流跟踪",
    location: "call_screen_pop",
    type: "iframe",
    enabled: false,
    defaultFocus: false,
    sortOrder: 2,
    updatedAt: "2026-07-28 09:40",
  },
  {
    id: 3,
    name: "会员档案",
    location: "chat_auxiliary",
    type: "iframe",
    enabled: true,
    defaultFocus: false,
    sortOrder: 1,
    updatedAt: "2026-08-03 10:15",
  },
  {
    id: 4,
    name: "服务提醒",
    location: "chat_auxiliary",
    type: "react_code",
    enabled: true,
    defaultFocus: false,
    sortOrder: 2,
    updatedAt: "2026-07-30 16:20",
  },
];

/** URL variable chips shown in the edit form, grouped by location. */
export const URL_VARIABLES: Record<EmbeddedPageLocation, string[]> = {
  chat_auxiliary: [
    "{conversation_id}",
    "{channel_type}",
    "{visitor_id}",
    "{visitor_name}",
    "{user_id}",
    "{agent_id}",
    "{agent_name}",
    "{agent_email}",
  ],
  call_screen_pop: [
    "{call_record_id}",
    "{direction}",
    "{customer_number}",
    "{queue_id}",
    "{user_id}",
    "{agent_id}",
    "{agent_name}",
    "{agent_email}",
  ],
};

export const REACT_CODE_SAMPLE = `export default function EmbeddedApp({ context, config, api }) {
  const visitor = context.visitor
  const items = Array.isArray(config.items) ? config.items : []

  return React.createElement('div', { className: 'panel' },
    React.createElement('h3', null, config.title || '服务提醒'),
    visitor
      ? React.createElement('p', null, '当前访客：' + visitor.name)
      : React.createElement('p', null, '暂无选中会话'),
    items.map((item) =>
      React.createElement('button', {
        key: item.id,
        onClick: () => api.openUrl(item.url),
      }, item.label)
    )
  )
}`;

export const CONFIG_JSON_SAMPLE = `{
  "title": "服务提醒",
  "items": [
    { "id": "sla", "label": "SLA 承诺", "url": "https://crm.example.com/sla" },
    { "id": "faq", "label": "高频问题", "url": "https://crm.example.com/faq" }
  ]
}`;
