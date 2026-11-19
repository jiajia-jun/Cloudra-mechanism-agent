import { useState } from 'react';

type ImageAttachment = { path: string; artifactId: string; name: string; size: number };
type Draft = { text: string; images: ImageAttachment[]; uploading: boolean };
const blank: Draft = { text: '', images: [], uploading: false };

export function useComposerDraft(projectId: string | null, agentId: string | null, questionId?: string | number) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const key = JSON.stringify([projectId, agentId, questionId ?? null]);
  const current = drafts[key] ?? blank;

  // Each render's setters retain the owner, including during an upload or send.
  function update(change: (previous: Draft) => Draft) {
    setDrafts(previous => {
      const next = change(previous[key] ?? blank);
      const result = { ...previous };
      if (next.text || next.images.length || next.uploading) result[key] = next;
      else delete result[key];
      return result;
    });
  }

  function adoptFirstAgent(id: string) {
    const destination = JSON.stringify([projectId, id, null]);
    setDrafts(previous => {
      const pending = previous[key];
      if (!pending || destination === key) return previous;
      const existing = previous[destination];
      const result = { ...previous };
      delete result[key];
      result[destination] = existing ? {
        text: [existing.text, pending.text].filter(Boolean).join('\n'),
        images: [...existing.images, ...pending.images],
        uploading: existing.uploading,
      } : pending;
      return result;
    });
  }

  return {
    draft: current.text, pendingImages: current.images, uploading: current.uploading,
    setDraft(text: string | ((old: string) => string)) {
      update(old => ({ ...old, text: typeof text === 'function' ? text(old.text) : text }));
    },
    setPendingImages(change: (images: ImageAttachment[]) => ImageAttachment[]) {
      update(old => ({ ...old, images: change(old.images) }));
    },
    setUploading(uploading: boolean) { update(old => ({ ...old, uploading })); },
    adoptFirstAgent,
  };
}
