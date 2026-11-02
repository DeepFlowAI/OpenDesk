import { describe, expect, it } from 'vitest'

import { sanitizeHtml } from './safe-html'

function parse(html: string): HTMLTemplateElement {
  const template = document.createElement('template')
  template.innerHTML = sanitizeHtml(html)
  return template
}

describe('sanitizeHtml', () => {
  it.each([
    ['<script>alert(1)</script>'],
    ['<img src=x onerror=alert(1)>'],
    ['<a href="javascript:alert(1)">x</a>'],
    ['<a href="jav&#x09;ascript:alert(1)">x</a>'],
    ['<a href=" &#14; javascript:alert(1)">x</a>'],
    ['<svg><a xlink:href="javascript:alert(1)"><text y="20">x</text></a></svg>'],
    ['<form action="javascript:alert(1)"><button>x</button></form>'],
    ['<iframe srcdoc="<script>alert(1)</script>"></iframe>'],
    ['<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>'],
    ['<details open ontoggle=alert(1)>'],
    ['<object data="javascript:alert(1)"></object>'],
  ])('neutralizes %s', (payload) => {
    const clean = sanitizeHtml(payload)
    expect(clean.toLowerCase()).not.toMatch(/javascript:|onerror|ontoggle|<script|<iframe|<object|<form/)
  })

  it('keeps rich-text formatting, links and images', () => {
    const html = [
      '<p style="color: red"><strong>bold</strong> <em>it</em> <u>u</u> <mark>m</mark></p>',
      '<ul><li>one</li></ul><ol><li>two</li></ol>',
      '<a href="https://example.com/a" target="_blank">link</a>',
      '<img src="https://cdn.example.com/a.png" data-file-id="f1" data-name="a.png" alt="a">',
      '<img src="blob:https://app.example.com/123" alt="local">',
      '<table><tbody><tr><td colspan="2">cell</td></tr></tbody></table>',
    ].join('')
    const root = parse(html).content

    expect(root.querySelector('strong')?.textContent).toBe('bold')
    expect(root.querySelector('p')?.getAttribute('style')).toContain('color')
    expect(root.querySelectorAll('li')).toHaveLength(2)
    expect(root.querySelector('td')?.getAttribute('colspan')).toBe('2')

    const link = root.querySelector('a')
    expect(link?.getAttribute('href')).toBe('https://example.com/a')
    expect(link?.getAttribute('target')).toBe('_blank')
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer')

    const [remote, local] = Array.from(root.querySelectorAll('img'))
    expect(remote.getAttribute('data-file-id')).toBe('f1')
    expect(remote.getAttribute('data-name')).toBe('a.png')
    expect(local.getAttribute('src')).toBe('blob:https://app.example.com/123')
  })

  it('keeps mailto and tel links', () => {
    const root = parse('<a href="mailto:a@example.com">m</a><a href="tel:+8610">t</a>').content
    const hrefs = Array.from(root.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['mailto:a@example.com', 'tel:+8610'])
  })

  it('returns empty string for empty input', () => {
    expect(sanitizeHtml('')).toBe('')
  })
})
