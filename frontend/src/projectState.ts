import type { Project } from './types';

// The server emits UTC ISO timestamps with optional microseconds. Padding
// preserves their order without losing precision to Date's milliseconds.
function timestamp(value: string): string {
  const [seconds, fraction = ''] = (value ?? '').replace('+00:00', 'Z').replace('Z', '').split('.');
  return `${seconds}.${fraction.padEnd(6, '0')}`;
}

export function mergeProjectSnapshot(current: Project | undefined, fresh: Project): Project {
  return current && timestamp(current.updated_at) > timestamp(fresh.updated_at) ? current : fresh;
}
