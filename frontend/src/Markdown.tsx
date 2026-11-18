import { memo, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { workbenchLink } from './molecularWorkbench';

// Shared renderer for assistant output: GFM tables/code + KaTeX math
// ($...$ inline, $$...$$ display).  Memoized: KaTeX/remark re-rendering every
// transcript bubble on each streaming token is a major source of jank during
// tool-heavy runs.
function Markdown({ text, onOpenStructure }: { text: string; onOpenStructure?: (path:string)=>void }) {
  const structureLink = (value:string | undefined, children:ReactNode) => {
    const path = value && workbenchLink(value);
    if (path && onOpenStructure) return <button className="wb-structure-link" title={path} onClick={()=>onOpenStructure(path)}>{children}</button>;
    return null;
  };
  return (
    <ReactMarkdown components={onOpenStructure ? {
      a:({href,children}) => structureLink(href,children) ?? <a href={href}>{children}</a>,
      code:({className,children}) => (!className && typeof children === 'string' && structureLink(children,children)) || <code className={className}>{children}</code>,
    } : undefined} remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
      {text}
    </ReactMarkdown>
  );
}

export default memo(Markdown);
