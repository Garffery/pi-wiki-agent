import { useEffect, useState } from "react";
import type { SessionTreeNode } from "../../types/events";
import { api } from "../../services/api";

interface Props {
  sessionId: string;
  onNavigate?: (entryId: string) => void;
}

export function SessionTree({ sessionId, onNavigate }: Props) {
  const [tree, setTree] = useState<SessionTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getSessionTree(sessionId)
      .then((data) => setTree(data.tree || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [sessionId]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleNodeClick = (node: SessionTreeNode) => {
    setSelectedId(node.entry.id);
    if (onNavigate && node.entry.type === "message") {
      onNavigate(node.entry.id);
    }
  };

  const renderNode = (node: SessionTreeNode, depth: number) => {
    const hasChildren = node.children.length > 0;
    const isExpanded = expanded.has(node.entry.id);
    const isSelected = selectedId === node.entry.id;
    const isMessage = node.entry.type === "message";
    const role = (node.entry as any).data?.role || node.entry.type;
    const isBranchPoint = hasChildren && node.children.length > 1;

    return (
      <div key={node.entry.id}>
        <button
          onClick={() => {
            if (hasChildren) toggleExpand(node.entry.id);
            handleNodeClick(node);
          }}
          className={`w-full text-left flex items-center gap-1.5 py-1.5 text-xs transition-colors ${
            isSelected
              ? "text-[var(--accent-text)] bg-[var(--accent-soft)] rounded"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          }`}
          style={{ paddingLeft: `${8 + depth * 14}px` }}
        >
          {/* Expand/collapse indicator */}
          <span className="w-3.5 flex-shrink-0 text-center">
            {hasChildren ? (
              <svg
                className={`w-3 h-3 inline-block transition-transform ${isExpanded ? "rotate-90" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            ) : (
              <span className="inline-block w-3" />
            )}
          </span>

          {/* Node icon */}
          <span className="flex-shrink-0">
            {isMessage ? (
              role === "user" ? (
                <svg className="w-3 h-3 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              ) : (
                <svg className="w-3 h-3 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              )
            ) : (
              <span className={`w-2 h-2 rounded-full inline-block ${
                node.entry.type === "compaction" ? "bg-amber-400" :
                node.entry.type === "model_change" ? "bg-green-400" :
                "bg-[var(--text-tertiary)]/40"
              }`} />
            )}
          </span>

          {/* Label */}
          <span className="truncate">
            {node.label || (isMessage ? (role === "user" ? "用户消息" : "AI 回复") : node.entry.type)}
            {isBranchPoint && (
              <span className="ml-1 text-[10px] text-[var(--accent-text)]">
                ({node.children.length} 分支)
              </span>
            )}
          </span>

          {/* Node ID for debug */}
          <span className="ml-auto text-[9px] text-[var(--text-tertiary)]/40 font-mono flex-shrink-0">
            {node.entry.id.slice(0, 4)}
          </span>
        </button>

        {/* Children */}
        {hasChildren && isExpanded && (
          <div>
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-xs text-[var(--text-tertiary)]">加载中...</div>
      </div>
    );
  }

  if (tree.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-4">
        <p className="text-xs text-[var(--text-tertiary)] text-center">
          暂无对话树数据。发送消息后刷新。
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-2 py-2">
      {tree.map((node) => renderNode(node, 0))}
    </div>
  );
}
