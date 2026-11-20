import type { DiagnosticCheck, DiagnosticGroup, UpdateCheckResult } from './types';

export const ONBOARDING_DISMISSED_KEY = 'cloudra:onboarding-dismissed';
export const UPDATE_DISMISSED_VERSION_KEY = 'cloudra:update-dismissed-version';

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem?(key: string): void;
}

export interface OnboardingStarter {
  id: string;
  mode: 'standard' | 'dag_record' | 'dag_guided';
  titleZh: string;
  titleEn: string;
  descZh: string;
  descEn: string;
  promptZh: string;
  promptEn: string;
}

export const ONBOARDING_STARTERS: OnboardingStarter[] = [
  {
    id: 'mechanism-exploration',
    mode: 'dag_guided',
    titleZh: '有机反应机理探索',
    titleEn: 'Organic Reaction Mechanism Exploration',
    descZh: '从反应物到产物系统搜寻过渡态、核验虚频与 IRC 路径，并沉淀机理图证据。',
    descEn: 'Search transition states, verify imaginary frequencies and IRC paths, and record mechanism graph evidence.',
    promptZh: '请帮我探索 [填写反应物] 到 [填写产物] 的反应机理，优先评估最可能的竞争路径并汇报关键过渡态与能垒；不确定之处请先向我确认。',
    promptEn: 'Please explore the reaction mechanism from [reactants] to [products], prioritize plausible competing pathways, and report key transition states and barriers; ask me if anything is ambiguous.',
  },
  {
    id: 'inspect-existing-logs',
    mode: 'standard',
    titleZh: '排查已有计算日志与虚频',
    titleEn: 'Inspect Existing QM Logs & Frequencies',
    descZh: '直接读取工作区中已有的 ORCA / Gaussian / XYZ 文件，检查收敛、虚频归属并给出下一步建议。',
    descEn: 'Audit existing ORCA / Gaussian / XYZ outputs in your workspace, verify convergence and imaginary modes, and propose next steps.',
    promptZh: '请检查当前工作目录中已有的计算输出与结构文件，总结每个物种的收敛状态、虚频情况和相对能量，并指出还需要补算或修正的步骤。',
    promptEn: 'Please inspect the existing calculation logs and geometries in the workspace, summarize convergence, imaginary frequencies, and relative energies, and identify what needs follow-up calculations.',
  },
  {
    id: 'literature-and-scripts',
    mode: 'standard',
    titleZh: '文献调研与数据处理脚本',
    titleEn: 'Literature Review & Analysis Scripts',
    descZh: '无需先配置量化软件，立刻开展文献检索、机理背景梳理或计算化学分析脚本编写。',
    descEn: 'Start immediately without local QM binaries—run literature surveys, background checks, or write chemistry analysis scripts.',
    promptZh: '请帮我调研 [填写课题或反应类型] 的代表性文献与主流计算方案（泛函、基组、溶剂模型），整理成简洁对比并附关键参考文献。',
    promptEn: 'Please survey representative literature and standard computational protocols (functionals, basis sets, solvation models) for [topic or reaction], and summarize key references.',
  },
];

export const DIAGNOSTIC_GROUP_ORDER: DiagnosticGroup[] = ['llm', 'chemistry', 'compute', 'storage'];

export function readOnboardingDismissed(storage: StorageLike | null | undefined): boolean {
  if (!storage) return false;
  try {
    return storage.getItem(ONBOARDING_DISMISSED_KEY) === 'true';
  } catch {
    return false;
  }
}

export function writeOnboardingDismissed(storage: StorageLike | null | undefined, dismissed: boolean): void {
  if (!storage) return;
  try {
    if (dismissed) {
      storage.setItem(ONBOARDING_DISMISSED_KEY, 'true');
    } else if (storage.removeItem) {
      storage.removeItem(ONBOARDING_DISMISSED_KEY);
    } else {
      storage.setItem(ONBOARDING_DISMISSED_KEY, 'false');
    }
  } catch {
    /* ignore storage quota / privacy mode failures */
  }
}

export function shouldAutoOpenOnboarding(params: {
  projectsLoaded: boolean;
  projectsCount: number;
  dismissed: boolean;
}): boolean {
  return params.projectsLoaded && params.projectsCount === 0 && !params.dismissed;
}

export function readDismissedUpdateVersion(storage: StorageLike | null | undefined): string {
  if (!storage) return '';
  try {
    return storage.getItem(UPDATE_DISMISSED_VERSION_KEY) ?? '';
  } catch {
    return '';
  }
}

export function writeDismissedUpdateVersion(storage: StorageLike | null | undefined, version: string): void {
  if (!storage) return;
  try {
    storage.setItem(UPDATE_DISMISSED_VERSION_KEY, version);
  } catch {
    /* ignore storage failures */
  }
}

export function shouldShowUpdateNotice(
  update: UpdateCheckResult | null | undefined,
  dismissedVersion: string,
): boolean {
  if (!update || update.status !== 'update_available') return false;
  const latest = (update.latest_version ?? '').trim();
  if (!latest) return false;
  return latest !== dismissedVersion;
}

export function groupDiagnosticsChecks(
  checks: DiagnosticCheck[] | null | undefined,
): Array<{ group: DiagnosticGroup; items: DiagnosticCheck[] }> {
  const list = Array.isArray(checks) ? checks : [];
  return DIAGNOSTIC_GROUP_ORDER
    .map((group) => ({ group, items: list.filter((item) => item.group === group) }))
    .filter((bucket) => bucket.items.length > 0);
}
