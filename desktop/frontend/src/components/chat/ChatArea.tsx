import { useEffect, useRef } from "react";
import { useChatStore } from "../../stores/chatStore";
import { MessageList } from "./MessageList";
import { StreamingMessage } from "./StreamingMessage";

export function ChatArea() {
  const messages = useChatStore((s) => s.messages);
  const streaming = useChatStore((s) => s.streaming);
  const scrollRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  useEffect(() => {
    if (autoScrollRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streaming]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 50;
  };

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto">
      {messages.length === 0 && !streaming && (
        <div className="flex flex-col items-center justify-center h-full px-6">
          <div className="text-center max-w-lg">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-violet-500 via-indigo-500 to-blue-500 flex items-center justify-center text-white text-3xl font-bold shadow-[var(--shadow-md)] shadow-violet-400/25">
              π
            </div>
            <h2 className="text-2xl font-semibold text-[var(--text-primary)] mb-2 tracking-tight">
              欢迎使用 Pi
            </h2>
            <p className="text-lg text-[var(--text-secondary)] mb-8 leading-relaxed">
              你的 AI 编程助手 — 提问、调试错误、<br />
              重构代码，或者探索新想法。
            </p>

            <div className="grid grid-cols-2 gap-3 max-w-md mx-auto">
              {[
                { icon: "?", label: "解释这段代码", desc: "粘贴代码进行分析" },
                { icon: "!", label: "调试错误", desc: "分享堆栈跟踪信息" },
                { icon: "↻", label: "重构函数", desc: "优化代码结构" },
                { icon: "+", label: "编写单元测试", desc: "生成测试用例" },
              ].map((hint) => (
                <div
                  key={hint.label}
                  className="text-left px-4 py-3 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] hover:border-[var(--accent)]/30 hover:bg-[var(--bg-card-hover)] transition-all cursor-default shadow-[var(--shadow-xs)]"
                >
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="w-5 h-5 rounded-lg bg-[var(--accent-soft)] flex items-center justify-center text-[var(--accent-text)] text-xs font-bold">
                      {hint.icon}
                    </span>
                    <span className="text-sm font-medium text-[var(--text-primary)]">{hint.label}</span>
                  </div>
                  <p className="text-sm text-[var(--text-tertiary)] ml-7">{hint.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="py-6" style={{ paddingLeft: 0, paddingRight: 64 }}>
        <MessageList messages={messages} />
        {streaming && <StreamingMessage streaming={streaming} />}
      </div>
    </div>
  );
}
