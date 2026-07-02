import { useState, useMemo, useCallback } from "react";

export interface CompletionItem {
  name: string;
  description: string;
}

export function useAutocomplete(
  items: CompletionItem[],
  value: string,
  trigger: string
) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const results = useMemo(() => {
    const lower = value.toLowerCase();
    return items.filter(
      (item) =>
        item.name.toLowerCase().includes(lower) ||
        item.description.toLowerCase().includes(lower)
    );
  }, [items, value]);

  const visible = value.startsWith(trigger) && results.length > 0;

  const reset = useCallback(() => {
    setSelectedIndex(0);
  }, []);

  const moveUp = useCallback(() => {
    setSelectedIndex((i) => (i > 0 ? i - 1 : results.length - 1));
  }, [results.length]);

  const moveDown = useCallback(() => {
    setSelectedIndex((i) => (i < results.length - 1 ? i + 1 : 0));
  }, [results.length]);

  return { results, selectedIndex, visible, reset, moveUp, moveDown, setSelectedIndex };
}
