import type { Locale } from '@/context/locale-store'
import type { EmojiItem } from '@/models/emoji-setting'

export const DEFAULT_EMOJI_ITEMS: EmojiItem[] = [
  { emoji: '👋', name: '你好', name_en: 'Hello', alias: '打招呼', alias_en: 'Wave', keywords: ['hello', 'hi', 'greeting'] },
  { emoji: '😊', name: '微笑', name_en: 'Smile', alias: '微笑', alias_en: 'Smile', keywords: ['happy', 'friendly'] },
  { emoji: '🙂', name: '好的', name_en: 'Okay', alias: '友好', alias_en: 'Friendly', keywords: ['ok', 'friendly'] },
  { emoji: '😄', name: '开心', name_en: 'Happy', alias: '开心', alias_en: 'Happy', keywords: ['joy', 'laugh'] },
  { emoji: '👍', name: '收到', name_en: 'Got it', alias: '收到', alias_en: 'Thumbs up', keywords: ['yes', 'agree'] },
  { emoji: '👌', name: 'OK', name_en: 'OK', alias: '可以', alias_en: 'Okay', keywords: ['ok', 'fine'] },
  { emoji: '🙏', name: '感谢', name_en: 'Thanks', alias: '感谢', alias_en: 'Thank you', keywords: ['thanks', 'please'] },
  { emoji: '🙇', name: '抱歉', name_en: 'Sorry', alias: '抱歉', alias_en: 'Apology', keywords: ['sorry', 'apologize'] },
  { emoji: '💪', name: '加油', name_en: 'Support', alias: '支持', alias_en: 'Support', keywords: ['strong', 'support'] },
  { emoji: '❤️', name: '喜欢', name_en: 'Love', alias: '爱心', alias_en: 'Heart', keywords: ['love', 'like'] },
  { emoji: '⭐', name: '满意', name_en: 'Satisfied', alias: '星标', alias_en: 'Star', keywords: ['star', 'satisfied'] },
  { emoji: '🎉', name: '恭喜', name_en: 'Congrats', alias: '庆祝', alias_en: 'Celebrate', keywords: ['party', 'celebrate'] },
  { emoji: '🎁', name: '礼物', name_en: 'Gift', alias: '福利', alias_en: 'Gift', keywords: ['gift', 'benefit'] },
  { emoji: '🔥', name: '热门', name_en: 'Hot', alias: '火热', alias_en: 'Fire', keywords: ['hot', 'popular'] },
  { emoji: '⏳', name: '等待', name_en: 'Waiting', alias: '等待', alias_en: 'Wait', keywords: ['wait', 'loading'] },
  { emoji: '👀', name: '看看', name_en: 'Check', alias: '查看', alias_en: 'Look', keywords: ['look', 'view'] },
  { emoji: '🤔', name: '思考', name_en: 'Thinking', alias: '思考', alias_en: 'Think', keywords: ['think', 'consider'] },
  { emoji: '❓', name: '疑问', name_en: 'Question', alias: '疑问', alias_en: 'Question', keywords: ['question', 'unknown'] },
  { emoji: '❗', name: '注意', name_en: 'Notice', alias: '提醒', alias_en: 'Alert', keywords: ['notice', 'important'] },
  { emoji: '📞', name: '电话', name_en: 'Phone', alias: '电话', alias_en: 'Phone', keywords: ['phone', 'call'] },
  { emoji: '✉️', name: '邮件', name_en: 'Email', alias: '邮件', alias_en: 'Email', keywords: ['mail', 'email'] },
  { emoji: '📄', name: '文件', name_en: 'File', alias: '文档', alias_en: 'Document', keywords: ['file', 'document'] },
  { emoji: '🔗', name: '链接', name_en: 'Link', alias: '链接', alias_en: 'Link', keywords: ['url', 'link'] },
  { emoji: '🛠️', name: '处理中', name_en: 'Fixing', alias: '工具 / 修复', alias_en: 'Tool / fix', keywords: ['tool', 'fix'] },
  { emoji: '✅', name: '已完成', name_en: 'Done', alias: '完成', alias_en: 'Complete', keywords: ['done', 'success'] },
  { emoji: '❌', name: '失败', name_en: 'Failed', alias: '错误', alias_en: 'Error', keywords: ['error', 'failed'] },
  { emoji: '😂', name: '大笑', name_en: 'Laughing', alias: '大笑', alias_en: 'Laugh', keywords: ['laugh', 'funny'] },
  { emoji: '🤣', name: '笑哭', name_en: 'ROFL', alias: '笑哭', alias_en: 'Laughing hard', keywords: ['laugh', 'tears'] },
  { emoji: '😅', name: '尴尬', name_en: 'Awkward', alias: '无奈', alias_en: 'Awkward', keywords: ['awkward', 'sweat'] },
  { emoji: '😢', name: '难过', name_en: 'Sad', alias: '难过', alias_en: 'Sad', keywords: ['sad', 'cry'] },
  { emoji: '😭', name: '大哭', name_en: 'Crying', alias: '大哭', alias_en: 'Crying', keywords: ['cry', 'sad'] },
  { emoji: '😞', name: '失望', name_en: 'Disappointed', alias: '失望', alias_en: 'Disappointed', keywords: ['disappointed'] },
  { emoji: '😕', name: '困惑', name_en: 'Confused', alias: '困惑', alias_en: 'Confused', keywords: ['confused'] },
  { emoji: '😮', name: '惊讶', name_en: 'Surprised', alias: '惊讶', alias_en: 'Surprised', keywords: ['surprise'] },
  { emoji: '😡', name: '生气', name_en: 'Angry', alias: '生气', alias_en: 'Angry', keywords: ['angry'] },
  { emoji: '🤯', name: '抓狂', name_en: 'Mind blown', alias: '抓狂', alias_en: 'Overwhelmed', keywords: ['mind blown'] },
  { emoji: '😩', name: '累了', name_en: 'Tired', alias: '累了', alias_en: 'Tired', keywords: ['tired'] },
  { emoji: '😟', name: '担心', name_en: 'Worried', alias: '担心', alias_en: 'Worried', keywords: ['worried'] },
]

const EXTRA_EMOJI_ROWS: Array<[string, string, string, string, string, string[]]> = [
  ['😀', '笑脸', 'Grinning', '笑脸', 'Grin', ['happy', 'smile']],
  ['😁', '露齿笑', 'Beaming', '笑', 'Beam', ['happy', 'grin']],
  ['😆', '眯眼笑', 'Squinting laugh', '笑', 'Laugh', ['happy', 'laugh']],
  ['😉', '眨眼', 'Wink', '提示', 'Wink', ['wink']],
  ['😍', '喜欢', 'Heart eyes', '爱心眼', 'Heart eyes', ['love']],
  ['😘', '飞吻', 'Kiss', '亲亲', 'Kiss', ['kiss']],
  ['😋', '好吃', 'Yummy', '美味', 'Yummy', ['food']],
  ['😎', '酷', 'Cool', '墨镜', 'Cool', ['cool']],
  ['😐', '平静', 'Neutral', '平静', 'Neutral', ['neutral']],
  ['😬', '龇牙', 'Grimace', '紧张', 'Grimace', ['nervous']],
  ['🙄', '无语', 'Eye roll', '无语', 'Eye roll', ['speechless']],
  ['😴', '困', 'Sleepy', '睡觉', 'Sleep', ['sleep']],
  ['🤝', '握手', 'Handshake', '合作', 'Handshake', ['deal', 'cooperate']],
  ['👏', '鼓掌', 'Clap', '赞赏', 'Clap', ['applause']],
  ['🙌', '庆祝', 'Raised hands', '举手', 'Celebrate', ['celebrate']],
  ['👎', '不赞同', 'Thumbs down', '反对', 'Disagree', ['no']],
  ['👊', '加油', 'Fist', '鼓励', 'Fist bump', ['support']],
  ['✌️', '胜利', 'Victory', '胜利', 'Victory', ['peace']],
  ['🤞', '祝愿', 'Fingers crossed', '好运', 'Good luck', ['luck']],
  ['🤗', '拥抱', 'Hug', '拥抱', 'Hug', ['hug']],
  ['💡', '灵感', 'Idea', '想法', 'Idea', ['idea']],
  ['📌', '固定', 'Pin', '标记', 'Pin', ['pin']],
  ['📎', '附件', 'Attachment', '附件', 'Attachment', ['file']],
  ['📷', '图片', 'Camera', '图片', 'Image', ['image', 'photo']],
  ['📢', '公告', 'Announcement', '广播', 'Announcement', ['announce']],
  ['🔔', '提醒', 'Bell', '提醒', 'Reminder', ['remind']],
  ['🔒', '安全', 'Lock', '锁定', 'Security', ['secure']],
  ['🔑', '密钥', 'Key', '钥匙', 'Key', ['key']],
  ['🚀', '上线', 'Launch', '启动', 'Launch', ['launch']],
  ['⚡', '快速', 'Fast', '闪电', 'Fast', ['fast']],
  ['💬', '消息', 'Message', '对话', 'Message', ['chat']],
  ['📝', '记录', 'Note', '备注', 'Note', ['note']],
  ['📅', '日程', 'Calendar', '日期', 'Calendar', ['date']],
  ['🕒', '时间', 'Time', '时间', 'Time', ['time']],
  ['💰', '费用', 'Money', '金额', 'Money', ['price', 'billing']],
  ['🛒', '购物车', 'Cart', '订单', 'Cart', ['order']],
  ['📦', '包裹', 'Package', '物流', 'Package', ['shipping']],
  ['🚚', '配送', 'Delivery', '配送', 'Delivery', ['delivery']],
  ['🏷️', '标签', 'Tag', '标签', 'Tag', ['tag']],
  ['🎫', '工单', 'Ticket', '票据', 'Ticket', ['ticket']],
  ['🔍', '搜索', 'Search', '查找', 'Search', ['search']],
  ['📍', '位置', 'Location', '定位', 'Location', ['location']],
  ['🌟', '推荐', 'Recommended', '闪耀', 'Recommended', ['recommend']],
  ['💯', '满分', 'Perfect', '满分', 'Perfect', ['perfect']],
  ['🏆', '奖杯', 'Trophy', '优秀', 'Trophy', ['award']],
  ['☕', '休息', 'Coffee', '咖啡', 'Coffee', ['break']],
  ['🍀', '幸运', 'Lucky', '幸运', 'Lucky', ['luck']],
  ['🌈', '顺利', 'Rainbow', '彩虹', 'Rainbow', ['hope']],
  ['☀️', '晴天', 'Sunny', '阳光', 'Sunny', ['sun']],
  ['🌙', '夜间', 'Moon', '月亮', 'Moon', ['night']],
  ['☁️', '云', 'Cloud', '云', 'Cloud', ['cloud']],
  ['☔', '雨', 'Rain', '雨伞', 'Rain', ['rain']],
]

export const ALL_EMOJI_ITEMS: EmojiItem[] = [
  ...DEFAULT_EMOJI_ITEMS,
  ...EXTRA_EMOJI_ROWS.map(([emoji, name, name_en, alias, alias_en, keywords]) => ({
    emoji,
    name,
    name_en,
    alias,
    alias_en,
    keywords,
  })),
].filter((item, index, items) => items.findIndex((candidate) => candidate.emoji === item.emoji) === index)

export function getEmojiName(item: EmojiItem, locale: Locale): string {
  if (locale === 'en') return item.name_en || item.name
  return item.name
}

export function getEmojiAlias(item: EmojiItem, locale: Locale): string {
  if (locale === 'en') return item.alias_en || item.alias || item.name_en || item.name
  return item.alias || item.name
}

export function getEmojiSearchText(item: EmojiItem): string {
  return [
    item.emoji,
    item.name,
    item.name_en,
    item.alias,
    item.alias_en,
    ...item.keywords,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}
