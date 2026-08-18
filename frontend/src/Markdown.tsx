import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

// Shared renderer for assistant output: GFM tables/code + KaTeX math
// ($...$ inline, $$...$$ display).  Memoized: KaTeX/remark re-rendering every
// transcript bubble on each streaming token is a major source of jank during
// tool-heavy runs.
function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
      {text}
    </ReactMarkdown>
  );
}

export default memo(Markdown);
