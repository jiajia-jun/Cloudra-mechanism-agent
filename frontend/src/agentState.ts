import type { Agent } from './types';

/** 快照可以纠正缓存；只有请求期间收到更新事件时，才保留实时运行投影。 */
export function mergeAgentSnapshot(current: Agent, fresh: Agent, preserveRuntime: boolean): Agent {
  if (!preserveRuntime) return fresh;
  return {
    ...fresh,
    state: current.state,
    current_run: current.current_run,
    current_task: current.current_task,
    completion: current.current_run ? null : current.completion,
  };
}

/** 项目快照和 cursor 是服务端同一边界；更新的 SSE（含后台 Agent）优先。 */
export function mergeProjectAgentSnapshot(
  current: Agent[], fresh: Agent[], cursor: number, latestSeq: ReadonlyMap<string, number>,
): Agent[] {
  const previous = new Map(current.map(agent => [agent.id, agent]));
  const ids = new Set(fresh.map(agent => agent.id));
  return [
    ...fresh.map(agent => {
      const cached = previous.get(agent.id);
      return cached ? mergeAgentSnapshot(cached, agent, (latestSeq.get(agent.id) ?? 0) > cursor) : agent;
    }),
    ...current.filter(agent => !ids.has(agent.id) && (latestSeq.get(agent.id) ?? 0) > cursor),
  ];
}
