/**
 * Tailwind v4 preflight resets rich-text elements globally.
 * Without @tailwindcss/typography, `prose` does not restore block styles.
 * Apply these classes on rich-text roots (TipTap ProseMirror, HTML display wrappers).
 */
export const richTextListStyleClass =
  [
    '[&_p]:my-1',
    '[&_h1]:my-2 [&_h1]:text-2xl [&_h1]:font-semibold [&_h1]:leading-tight',
    '[&_h2]:my-2 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:leading-tight',
    '[&_h3]:my-2 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:leading-snug',
    '[&_h4]:my-2 [&_h4]:text-base [&_h4]:font-semibold',
    '[&_h5]:my-2 [&_h5]:text-sm [&_h5]:font-semibold',
    '[&_h6]:my-2 [&_h6]:text-xs [&_h6]:font-semibold',
    '[&_blockquote]:my-2 [&_blockquote]:border-l-4 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:text-muted-foreground [&_blockquote_p]:my-0',
    '[&_ul]:my-1 [&_ul]:list-disc [&_ul]:ps-6',
    '[&_ol]:my-1 [&_ol]:list-decimal [&_ol]:ps-6',
    '[&_li]:my-0.5 [&_li_p]:my-0',
    '[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2',
    '[&_code]:rounded-sm [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.9em]',
    '[&_img]:my-2 [&_img]:max-w-full [&_img]:rounded-md [&_img]:border [&_img]:border-border',
    '[&_table]:my-3 [&_table]:w-max [&_table]:min-w-max [&_table]:border-collapse [&_table]:text-left [&_table]:text-sm [&_table]:leading-7 [&_table]:text-[#111827]',
    '[&_thead]:bg-white',
    '[&_tbody_tr:nth-child(even)]:bg-[#F8FAFC]',
    '[&_th]:border [&_th]:border-[#CBD5E1] [&_th]:bg-white [&_th]:px-4 [&_th]:py-3 [&_th]:text-center [&_th]:font-semibold [&_th]:text-[#111827] [&_th]:align-middle',
    '[&_td]:border [&_td]:border-[#CBD5E1] [&_td]:px-4 [&_td]:py-3 [&_td]:align-middle',
    '[&_mark]:rounded-sm [&_mark]:px-px',
  ].join(' ')
