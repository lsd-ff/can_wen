import { useState, type ReactNode } from 'react';
import { Check, Copy } from 'lucide-react';

type MarkdownBlock =
  | { type: 'heading'; level: 1 | 2 | 3; content: string }
  | { type: 'paragraph'; lines: string[] }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'quote'; lines: string[] }
  | { type: 'code'; language: string; code: string }
  | { type: 'divider' };

const blockStartPattern = /^(?:#{1,3}\s+|>\s?|[-*+]\s+|\d+[.)]\s+|```|---+\s*$)/;
const inlineTokenPattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\((?:https?:\/\/)[^)\s]+\))/g;

function safeExternalUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch {
    return null;
  }
}

function renderInlineMarkdown(value: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;

  for (const match of value.matchAll(inlineTokenPattern)) {
    const token = match[0];
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(value.slice(cursor, start));

    if (token.startsWith('`')) {
      nodes.push(<code className="diagnosis-markdown-inline-code" key={`code-${start}`}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith('**')) {
      nodes.push(<strong key={`strong-${start}`}>{token.slice(2, -2)}</strong>);
    } else {
      const linkMatch = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const href = linkMatch ? safeExternalUrl(linkMatch[2]) : null;
      nodes.push(
        href ? (
          <a href={href} key={`link-${start}`} rel="noreferrer" target="_blank">
            {linkMatch?.[1]}
          </a>
        ) : (
          token
        ),
      );
    }
    cursor = start + token.length;
  }

  if (cursor < value.length) nodes.push(value.slice(cursor));
  return nodes;
}

function parseDiagnosisMarkdown(content: string): MarkdownBlock[] {
  const lines = content.replace(/\r/g, '').split('\n');
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const codeStart = line.match(/^```\s*([^\s]*)/);
    if (codeStart) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: 'code', language: codeStart[1] || 'text', code: codeLines.join('\n') });
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length as 1 | 2 | 3, content: heading[2].trim() });
      index += 1;
      continue;
    }

    if (/^---+\s*$/.test(line)) {
      blocks.push({ type: 'divider' });
      index += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^>\s?/, '').trim());
        index += 1;
      }
      blocks.push({ type: 'quote', lines: quoteLines });
      continue;
    }

    const unordered = line.match(/^[-*+]\s+(.+)$/);
    const ordered = line.match(/^\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      const itemPattern = unordered ? /^[-*+]\s+(.+)$/ : /^\d+[.)]\s+(.+)$/;
      const items: string[] = [];
      while (index < lines.length) {
        const item = lines[index].match(itemPattern);
        if (!item) break;
        items.push(item[1].trim());
        index += 1;
      }
      blocks.push({ type: 'list', ordered: Boolean(ordered), items });
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length && lines[index].trim() && !blockStartPattern.test(lines[index])) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    if (paragraphLines.length > 0) {
      blocks.push({ type: 'paragraph', lines: paragraphLines });
      continue;
    }
    index += 1;
  }

  return blocks;
}

function copyCode(code: string) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(code);

  const textarea = document.createElement('textarea');
  textarea.value = code;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();
  return copied ? Promise.resolve() : Promise.reject(new Error('无法复制代码'));
}

function DiagnosisCodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    void copyCode(code)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1800);
      })
      .catch(() => setCopied(false));
  };

  return (
    <section className="diagnosis-markdown-code-block" aria-label={`${language} 代码片段`}>
      <header>
        <span>{language}</span>
        <button type="button" onClick={handleCopy}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          <span>{copied ? '已复制' : '复制'}</span>
        </button>
      </header>
      <pre><code>{code}</code></pre>
    </section>
  );
}

export function DiagnosisMarkdown({ content }: { content: string }) {
  const blocks = parseDiagnosisMarkdown(content);

  if (blocks.length === 0) return null;

  return (
    <div className="diagnosis-markdown">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const Heading = `h${block.level}` as 'h1' | 'h2' | 'h3';
          return <Heading className={`diagnosis-markdown-heading level-${block.level}`} key={`heading-${index}`}>{renderInlineMarkdown(block.content)}</Heading>;
        }

        if (block.type === 'paragraph') {
          return (
            <p className="diagnosis-markdown-paragraph" key={`paragraph-${index}`}>
              {block.lines.map((line, lineIndex) => (
                <span key={`${line}-${lineIndex}`}>
                  {lineIndex > 0 && <br />}
                  {renderInlineMarkdown(line)}
                </span>
              ))}
            </p>
          );
        }

        if (block.type === 'list') {
          const List = block.ordered ? 'ol' : 'ul';
          return <List className="diagnosis-markdown-list" key={`list-${index}`}>{block.items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>)}</List>;
        }

        if (block.type === 'quote') {
          return <blockquote className="diagnosis-markdown-quote" key={`quote-${index}`}>{block.lines.map((line, lineIndex) => <span key={`${line}-${lineIndex}`}>{lineIndex > 0 && <br />}{renderInlineMarkdown(line)}</span>)}</blockquote>;
        }

        if (block.type === 'code') {
          return <DiagnosisCodeBlock code={block.code} key={`code-${index}`} language={block.language} />;
        }

        return <hr className="diagnosis-markdown-divider" key={`divider-${index}`} />;
      })}
    </div>
  );
}
