import type { Components } from 'react-markdown';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type ChatMarkdownProps = {
  text: string;
};

const mdComponents: Components = {
  table: ({ children }) => (
    <div className="agent-md-table-wrap">
      <table className="agent-md-table">{children}</table>
    </div>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="agent-md-link">
      {children}
    </a>
  ),
};

export function ChatMarkdown({ text }: ChatMarkdownProps) {
  const source = text.replace(/\r\n/g, '\n').trim();
  return (
    <div className="chat-md agent-chat-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {source}
      </ReactMarkdown>
    </div>
  );
}
