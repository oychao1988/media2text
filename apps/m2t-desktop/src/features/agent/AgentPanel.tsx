import { useMemo } from 'react';
import { ChatMarkdown } from './ChatMarkdown';
import { AgentComposer } from './AgentComposer';
import { ToolResultCard } from './ToolResultCard';
import { useM2tAgent } from './useM2tAgent';

type AgentPanelProps = {
  creatorId: string | null;
  sessionId: string | null;
  playbackMode?: boolean;
};

function AgentChatMessages({
  agent,
}: {
  agent: ReturnType<typeof useM2tAgent>;
}) {
  return (
    <>
      {agent.messages.map((msg) => {
        if (msg.role === 'user') {
          return (
            <div key={msg.id} className="msg msg-user">
              <ChatMarkdown text={msg.text} />
            </div>
          );
        }
        if (msg.role === 'tool') {
          return (
            <div key={msg.id} className="msg msg-assistant">
              <ToolResultCard result={msg.result.payload} />
            </div>
          );
        }
        return (
          <div key={msg.id} className="msg msg-assistant">
            {msg.thinkingText ? (
              <div className="thinking">
                <ChatMarkdown text={msg.thinkingText} />
              </div>
            ) : null}
            <ChatMarkdown text={msg.text} />
          </div>
        );
      })}
      {agent.activeTurn ? (
        <div className="msg msg-assistant">
          <p className="muted agent-phase">{agent.activeTurn.phaseLabel}</p>
          {agent.activeTurn.thinkingText ? (
            <div className="thinking">
              <ChatMarkdown text={agent.activeTurn.thinkingText} />
            </div>
          ) : null}
          {agent.activeTurn.assistantText ? (
            <ChatMarkdown text={agent.activeTurn.assistantText} />
          ) : null}
        </div>
      ) : null}
      {agent.status === 'crashed' ? (
        <p className="muted agent-status-hint">Agent 已退出，正在尝试恢复…</p>
      ) : null}
    </>
  );
}

export function AgentPanel({ creatorId, sessionId, playbackMode = false }: AgentPanelProps) {
  const agent = useM2tAgent({ creatorId, sessionId });

  const modelOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of agent.providers) {
      for (const m of p.models ?? []) set.add(m);
    }
    return [...set];
  }, [agent.providers]);

  const modelPill = agent.threadModel && agent.threadModel !== 'auto' ? agent.threadModel : 'auto';

  if (agent.fatalError && agent.status === 'error') {
    return (
      <section className="agent-pane agent-pane--error" aria-label="Agent">
        <div className="agent-header">
          <span>Agent</span>
          <span className="model-pill">—</span>
        </div>
        <div className="chat-scroll" id="chat-scroll" role="alert">
          <p className="agent-error-title">Agent 不可用</p>
          <p className="muted">{agent.fatalError}</p>
          <p className="muted agent-error-hint">监控与转写不受影响，请检查 LLM 配置后重试。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="agent-pane" aria-label="Agent">
      <div className="agent-header">
        <span>Agent</span>
        <span className="model-pill">{modelPill}</span>
      </div>
      <div className="chat-scroll" id="chat-scroll" aria-live="polite">
        <div id="chat-live" style={playbackMode ? { display: 'none' } : undefined}>
          {!playbackMode ? <AgentChatMessages agent={agent} /> : null}
        </div>
        <div id="chat-playback" style={playbackMode ? undefined : { display: 'none' }}>
          {playbackMode ? <AgentChatMessages agent={agent} /> : null}
        </div>
      </div>
      <AgentComposer
        ready={agent.ready}
        model={agent.threadModel}
        providerModels={modelOptions}
        onModelChange={(m) => void agent.patchThreadModel(m)}
        onSend={(t) => void agent.sendMessage(t)}
      />
    </section>
  );
}
