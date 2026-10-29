export const AGENT_NAME = "移动客服助手"

export type TranscriptRole = "user" | "bot" | "agent"

export interface TranscriptLine {
  role: TranscriptRole
  text: string
  /** Caller barged in. The text is only the part already heard. */
  interrupted?: boolean
}

/** Greeting and one reply were cut off mid-playback. A reply cut off before any audio is omitted. */
export const botConversation: TranscriptLine[] = [
  { role: "bot", text: "您好，我是移动客服，", interrupted: true },
  { role: "user", text: "我的流量这个月超了，想改成不限量套餐。" },
  { role: "bot", text: "您可以在营业厅或线上变更为畅享不限量，变更后立即生效，本月已产生的超额费用仍按原套餐结算。" },
  { role: "bot", text: "变更需要先验证机主身份，", interrupted: true },
  { role: "user", text: "那我直接找人工吧。" },
  { role: "bot", text: "好的，正在为您转接人工客服，请稍候。" },
]

/** interrupted is true but the heard portion was never recorded, so the full reply stays. */
export const unrecordedInterrupt: TranscriptLine[] = [
  { role: "bot", text: "您好，请问有什么可以帮您？" },
  { role: "user", text: "帮我查一下宽带装机进度。" },
  {
    role: "bot",
    text: "请提供装机地址和联系电话，我帮您查询工单进度，一般两个工作日内有结果。",
    interrupted: true,
  },
  { role: "user", text: "算了，转人工。" },
  { role: "bot", text: "好的，正在为您转接人工客服，请稍候。" },
]

export const agentConversation: TranscriptLine[] = [
  { role: "user", text: "对，改成不限量，身份证尾号 1024。" },
  { role: "agent", text: "好的，我帮您核实一下机主信息，请稍等。" },
]

export const HANDOFF_TIME = "19:21:06"
