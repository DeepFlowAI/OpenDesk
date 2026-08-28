export const CALL = {
  status: "通话中",
  number: "18601123206",
  duration: "00:12",
  holdDuration: "00:08",
  consultName: "李敏",
  customerName: "张伟",
} as const;

export const ICON_LEGEND = [
  { name: "静音", desc: "关闭或恢复自己的麦克风" },
  { name: "保持", desc: "客户听等待音；再次点击恢复" },
  { name: "按键", desc: "打开拨号盘，向对方发送 DTMF" },
  { name: "短信", desc: "向当前号码发送短信" },
  { name: "转接", desc: "直接转给员工、队列或外部号码" },
  { name: "咨询", desc: "客户自动保持，先与第三方沟通" },
  { name: "三方", desc: "呼叫第三人并合并为三方" },
  { name: "评价", desc: "结束人工服务，客户继续评价" },
  { name: "挂断", desc: "只结束客户通话" },
] as const;
