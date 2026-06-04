import ReactMarkdown from 'react-markdown';

type ChatMarkdownProps = {
  text: string;
};

export function ChatMarkdown({ text }: ChatMarkdownProps) {
  const source = text.replace(/\r\n/g, '\n').trim();
  return (
    <div className="chat-md agent-chat-md">
      <ReactMarkdown>{source}</ReactMarkdown>
    </div>
  );
}
