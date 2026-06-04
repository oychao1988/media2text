import { useMemo } from 'react';
import { ChatMarkdown } from './ChatMarkdown';
import { AgentComposer } from './AgentComposer';
import { ToolResultCard } from './ToolResultCard';
import { useM2tAgent } from './useM2tAgent';

type AgentPanelProps = {
  creatorId: string | null;
  sessionId: string | null;
};

export function AgentPanel({ creatorId, sessionId }: AgentPanelProps) {
  const agent = useM2tAgent({ creatorId, sessionId });

  const modelOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of agent.providers) {
      for (const m of p.models ?? []) set.add(m);
    }
    return [...set];
  }, [agent.providers]);

  if (agent.fatalError && agent.status === 'error') {
    return (
      <div className="agent-panel agent-panel--error" role="alert">
        <p className="agent-error-title">Agent 不可用</p>
        <p className="muted">{agent.fatalError}</p>
        <p className="muted agent-error-hint">监控与转写不受影响，请检查 LLM 配置后重试。</p>
      </div>
    );
  }

  return (
    <div className="agent-panel">
      <div className="agent-messages" aria-live="polite">
        {agent.messages.map((msg) => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="agent-msg agent-msg--user">
                <ChatMarkdown text={msg.text} />
              </div>
            );
          }
          if (msg.role === 'tool') {
            return (
              <div key={msg.id} className="agent-msg agent-msg--tool">
                <ToolResultCard result={msg.result.payload} />
              </div>
            );
          }
          return (
            <div key={msg.id} className="agent-msg agent-msg--assistant">
              {msg.thinkingText ? (
                <details className="agent-thinking">
                  <summary>思考过程</summary>
                  <ChatMarkdown text={msg.thinkingText} />
                </details>
              ) : null}
              <ChatMarkdown text={msg.text} />
            </div>
          );
        })}
        {agent.activeTurn ? (
          <div className="agent-msg agent-msg--assistant agent-msg--streaming">
            <p className="muted agent-phase">{agent.activeTurn.phaseLabel}</p>
            {agent.activeTurn.thinkingText ? (
              <details className="agent-thinking" open>
                <summary>思考中…</summary>
                <ChatMarkdown text={agent.activeTurn.thinkingText} />
              </details>
            ) : null}
            {agent.activeTurn.assistantText ? (
              <ChatMarkdown text={agent.activeTurn.assistantText} />
            ) : null}
          </div>
        ) : null}
        {agent.status === 'crashed' ? (
          <p className="muted agent-status-hint">Agent 已退出，正在尝试恢复…</p>
        ) : null}
      </div>
      <AgentComposer
        ready={agent.ready}
        model={agent.threadModel}
        providerModels={modelOptions}
        onModelChange={(m) => void agent.patchThreadModel(m)}
        onSend={(t) => void agent.sendMessage(t)}
      />
    </div>
  );
}
