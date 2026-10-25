import { useSyncExternalStore } from 'react';

export const APPEARANCES = [
  { id: 'modernism', zh: '现代主义', en: 'Modernism' },
  { id: 'punk', zh: '朋克', en: 'Punk' },
  { id: 'acid', zh: 'Acid', en: 'Acid' },
] as const;

export type Appearance = typeof APPEARANCES[number]['id'];

const STORAGE_KEY = 'cloudra.appearance';
const CHANGE_EVENT = 'cloudra:appearance';

export function readAppearance(): Appearance {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return APPEARANCES.find((appearance) => appearance.id === saved)?.id ?? 'modernism';
  } catch {
    return 'modernism';
  }
}

export function applyAppearance(appearance: Appearance): void {
  // 外观只切换根节点样式，项目、Agent 和工作台视图不参与这份偏好。
  document.documentElement.dataset.appearance = appearance;
  try {
    localStorage.setItem(STORAGE_KEY, appearance);
  } catch {
    // 浏览器禁止存储时，本次页面仍可切换外观。
  }
  // Canvas 和 SVG 订阅同一次外观切换，不重建项目或重置视角。
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function activeAppearance(): Appearance {
  return APPEARANCES.find((appearance) => appearance.id === document.documentElement.dataset.appearance)?.id ?? readAppearance();
}

function subscribeAppearance(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => window.removeEventListener(CHANGE_EVENT, onChange);
}

export function useAppearance(): Appearance {
  return useSyncExternalStore(subscribeAppearance, activeAppearance);
}
