import type { KeyboardEvent, RefObject } from 'react';
import type { Translations } from './i18n';

export function LongTextControls({ expanded, onExpand, textarea, id, t }: {
  id: string; expanded: boolean; onExpand: (expand: boolean) => void;
  textarea: RefObject<HTMLTextAreaElement | null>; t: Translations;
}) {
  return <>
    <button type="button" className="btn ghost sm" aria-expanded={expanded} aria-controls={id}
      onClick={() => { onExpand(!expanded); textarea.current?.focus({ preventScroll: true }); }}>
      {expanded ? t.collapseLongText : t.expandLongText}
    </button>
    <span className="composer-hint">{expanded ? t.longTextKeys : t.compactTextKeys}</span>
  </>;
}

export function handleLongTextKey(event: KeyboardEvent<HTMLTextAreaElement>, submit: () => void, collapse: () => void) {
  if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    collapse();
  } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    if (!event.repeat) submit();
  }
}
