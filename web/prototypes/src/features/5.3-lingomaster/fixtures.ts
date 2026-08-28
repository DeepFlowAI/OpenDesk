export const DEFAULT_VISITOR_PROMPT = `你是客服场景的实时翻译引擎。请将以下{{source_language}}的访客消息翻译为{{target_language}}。
要求：准确保留原意与语气；品牌名、产品名、型号、URL、代码片段保持原文不译；只输出译文，不要输出任何解释。
以下会话历史均为双方消息原文，仅用于理解上下文：
{{conversation_history}}
当前消息：{{message}}`;

export const DEFAULT_AGENT_PROMPT = `你是客服场景的实时翻译引擎。请将以下{{source_language}}的客服消息翻译为{{target_language}}。
要求：准确保留原意与语气；品牌名、产品名、型号、URL、代码片段保持原文不译；只输出译文，不要输出任何解释。
以下会话历史均为双方消息原文，仅用于理解上下文：
{{conversation_history}}
当前消息：{{message}}`;

export const INVALID_AGENT_PROMPT = `你是客服场景的实时翻译引擎。请将访客语言翻译为客服语言，只输出译文。`;

export const PROMPT_VARIABLES = [
  { name: "{{message}}", description: "待翻译的消息原文", required: true },
  { name: "{{conversation_history}}", description: "会话开始至当前消息前的双方消息原文", required: false },
  { name: "{{source_language}}", description: "源语种名称（如 中文、English、日本語）", required: false },
  { name: "{{target_language}}", description: "目标语种名称", required: false },
];

/* ── Workspace demo fixtures ─────────────────────────────── */

/** 15 interface languages, native names only (per 系统多语言扩展 §1.2). */
export const INTERFACE_LANGUAGES: Array<{ code: string; nativeName: string }> = [
  { code: "zh", nativeName: "中文" },
  { code: "en", nativeName: "English" },
  { code: "fr-FR", nativeName: "Français" },
  { code: "es-ES", nativeName: "Español (España)" },
  { code: "es-419", nativeName: "Español (Latinoamérica)" },
  { code: "pt-BR", nativeName: "Português (Brasil)" },
  { code: "pt-PT", nativeName: "Português (Portugal)" },
  { code: "it-IT", nativeName: "Italiano" },
  { code: "nl-NL", nativeName: "Nederlands" },
  { code: "pl-PL", nativeName: "Polski" },
  { code: "ru-RU", nativeName: "Русский" },
  { code: "tr-TR", nativeName: "Türkçe" },
  { code: "th-TH", nativeName: "ไทย" },
  { code: "vi-VN", nativeName: "Tiếng Việt" },
  { code: "id-ID", nativeName: "Bahasa Indonesia" },
];

export const DEMO_VISITOR = {
  name: "田中 花子",
  /** Out-of-list language: shown as uppercase ISO code per PRD §3.5. */
  languageCode: "JA",
  languageName: "日本語",
  languageSource: "由访客消息自动检测",
  channel: "Web SDK",
};

export const DEMO_AGENT = { name: "李婷", languageName: "中文" };

export type TranslationState = "translated" | "failed";

export interface DemoMessage {
  id: number;
  sender: "visitor" | "agent";
  /** Visitor messages: Japanese original. Agent messages: Chinese original. */
  original: string;
  /** Visitor messages: Chinese translation shown by default. Agent messages: Japanese translation sent to the visitor. */
  translation: string;
  state: TranslationState;
  time: string;
}

export const DEMO_MESSAGES: DemoMessage[] = [
  {
    id: 1,
    sender: "visitor",
    original: "こんにちは。注文した商品がまだ届いていないのですが、確認できますか？",
    translation: "你好，我订购的商品还没有收到，可以帮我确认一下吗？",
    state: "translated",
    time: "14:32",
  },
  {
    id: 2,
    sender: "agent",
    original: "您好，请提供一下订单号，我马上为您查询。",
    translation: "ご注文番号をお教えいただけますか。すぐにお調べします。",
    state: "translated",
    time: "14:33",
  },
  {
    id: 3,
    sender: "visitor",
    original: "注文番号は OD-20260731-5821 です。マンションの宅配ボックスにも入っていませんでした。",
    translation: "订单号是 OD-20260731-5821。快递柜里也没有收到。",
    state: "translated",
    time: "14:34",
  },
];

export const DEMO_CONVERSATIONS = [
  { name: "田中 花子", snippet: "订单号是 OD-20260731-5821…", time: "14:34", active: true, unread: 0, color: "#4A8C5C" },
  { name: "Maria Silva", snippet: "Obrigada!", time: "13:12", active: false, unread: 2, color: "#8C5A4A" },
  { name: "王建国", snippet: "好的，谢谢！", time: "12:58", active: false, unread: 0, color: "#4A6B8C" },
  { name: "陈小明", snippet: "请问发票可以重开吗", time: "11:40", active: false, unread: 0, color: "#7A5A9A" },
  { name: "John Miller", snippet: "I still need help with my order", time: "09:27", active: false, unread: 0, color: "#927044" },
];

export const DIRECT_SEND_DRAFT = "お荷物は明日の午前中にお届け予定です。到着まで今しばらくお待ちください。";

export const FAILED_TRANSLATION_DRAFT = "已为您查到订单，包裹预计明天上午送达，请注意查收。";
