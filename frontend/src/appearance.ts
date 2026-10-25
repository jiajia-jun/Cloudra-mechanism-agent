export const APPEARANCES = [
  { id: 'original', zh: '原版工作台', en: 'Original workbench' },
  { id: 'glass', zh: '浅蓝玻璃', en: 'Sky glass' },
  { id: 'emerald', zh: '暗绿终端', en: 'Green terminal' },
] as const;

export type Appearance = typeof APPEARANCES[number]['id'];

const STORAGE_KEY = 'cloudra.appearance';

export function readAppearance(): Appearance {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return APPEARANCES.find((appearance) => appearance.id === saved)?.id ?? 'original';
  } catch {
    return 'original';
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
}
