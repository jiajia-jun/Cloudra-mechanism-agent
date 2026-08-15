import { useEffect, useMemo, useState } from 'react';
import { api, streamProject } from './api';
import type { Agent, EventEnvelope, Project, TranscriptMessage } from './types';

function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  useEffect(() => {
    api.listProjects().then(setProjects);
  }, []);
  const refresh = () => api.listProjects().then(setProjects);
  return { projects, activeId, setActiveId, refresh };
}

function Inspector({ activeAgent, activeProject, events, selectedEvent, onSelectEvent, onPatchSettings }: {
  activeAgent: Agent | null;
  activeProject: Project | null;
  events: EventEnvelope[];
  selectedEvent: EventEnvelope | null;
  onSelectEvent: (e: EventEnvelope) => void;
  onPatchSettings: (patch: Record<string, unknown>) => void;
}) {
  const [tab, setTab] = useState<'events' | 'dag' | 'approvals' | 'interactions' | 'artifacts' | 'settings'>('events');
  const [dag, setDag] = useState<Record<string, unknown> | null>(null);
  const [mutationDraft, setMutationDraft] = useState('');
  const [approvals, setApprovals] = useState<Array<Record<string, unknown>>>([]);
  const [artifacts, setArtifacts] = useState<Array<Record<string, unknown>>>([]);
  const [interactions, setInteractions] = useState<Array<Record<string, unknown>>>([]);

  async function loadTab(next: typeof tab) {
    setTab(next);
    if (!activeProject) return;
    if (next === 'dag') {
      const [graph, report] = await Promise.all([
        api.dagDelivery(activeProject.id),
        api.dagReport(activeProject.id),
      ]);
      setDag({ graph, report });
    } else if (next === 'approvals') setApprovals(await api.approvals(activeProject.id));
    else if (next === 'interactions') setInteractions(await api.interactions(activeProject.id));
    else if (next === 'artifacts') setArtifacts(await api.artifacts(activeProject.id));
  }

  return (
    <aside style={{ width: 420, borderLeft: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', gap: 4, padding: 8, borderBottom: '1px solid #333' }}>
        {(['events', 'dag', 'approvals', 'interactions', 'artifacts', 'settings'] as const).map((t) => (
          <button key={t} onClick={() => loadTab(t)} style={{ flex: 1, background: tab === t ? '#2a4a6a' : '#222', border: '1px solid #444', borderRadius: 6, padding: '4px 0', color: '#eee' }}>
            {t}
          </button>
        ))}
      </div>

      {tab === 'events' && (
        <>
          <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
            {events.map((event) => (
              <button key={event.event_id} onClick={() => onSelectEvent(event)}
                style={{ display: 'block', width: '100%', textAlign: 'left', background: selectedEvent?.event_id === event.event_id ? '#2a4a6a' : '#1a1a1a', border: '1px solid #333', borderRadius: 6, padding: 6, marginBottom: 4, color: '#eee' }}>
                <span style={{ color: '#aaa' }}>#{event.session_seq ?? '?'}</span> {event.type}
              </button>
            ))}
          </div>
          <div style={{ height: 220, overflow: 'auto', borderTop: '1px solid #333', padding: 8 }}>
            {selectedEvent ? <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{JSON.stringify(selectedEvent, null, 2)}</pre>
              : <div style={{ color: '#888', fontSize: 12 }}>select an event to inspect</div>}
          </div>
        </>
      )}

      {tab === 'dag' && (
        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {dag ? <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{JSON.stringify(dag, null, 2)}</pre>
            : <div style={{ color: '#888', fontSize: 12 }}>load DAG…</div>}
          {activeProject && (
            <div style={{ borderTop: '1px solid #333', paddingTop: 8 }}>
              <textarea
                value={mutationDraft}
                onChange={(e) => setMutationDraft(e.target.value)}
                placeholder='[{"op":"add_node","graph":"process","node":{...}}]'
                style={{ width: '100%', height: 80, fontSize: 11 }}
              />
              <button
                onClick={async () => {
                  try {
                    const ops = JSON.parse(mutationDraft || '[]');
                    await api.dagMutations(activeProject.id, ops, {}, 'manual UI mutation');
                    const [graph, report] = await Promise.all([
                      api.dagDelivery(activeProject.id),
                      api.dagReport(activeProject.id),
                    ]);
                    setDag({ graph, report });
                    setMutationDraft('');
                  } catch (err) {
                    setDag((prev) => ({ ...(prev ?? {}), error: err instanceof Error ? err.message : String(err) }));
                  }
                }}
              >
                apply mutation
              </button>
            </div>
          )}
        </div>
      )}

      {tab === 'approvals' && (
        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {approvals.map((approval) => (
            <div key={String(approval.id)} style={{ border: '1px solid #444', borderRadius: 6, padding: 8, marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: '#aaa' }}>{String(approval.id)} · {String(approval.tool_name ?? approval.tool ?? '')}</div>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{JSON.stringify(approval, null, 2)}</pre>
              {activeProject && (
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  <button onClick={() => api.decideApproval(activeProject.id, approval.id as number, 'approve').then(() => loadTab('approvals'))}>approve</button>
                  <button onClick={() => api.decideApproval(activeProject.id, approval.id as number, 'deny', 'denied by user').then(() => loadTab('approvals'))}>deny</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'interactions' && (
        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {interactions.map((item) => {
            const interactionId = item.interaction_id as number | string | undefined;
            return (
              <div key={String(interactionId ?? item.id ?? '')} style={{ border: '1px solid #444', borderRadius: 6, padding: 8, marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: '#aaa' }}>{String(item.session_id ?? '')}</div>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{JSON.stringify(item, null, 2)}</pre>
                {activeProject && interactionId && (
                  <input
                    placeholder="respond…"
                    onKeyDown={async (e) => {
                      if (e.key !== 'Enter') return;
                      await api.respondInteraction(activeProject.id, interactionId, (e.target as HTMLInputElement).value);
                      setInteractions(await api.interactions(activeProject.id));
                    }}
                    style={{ width: '100%', marginTop: 6 }}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {tab === 'artifacts' && (
        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {artifacts.map((artifact) => (
            <div key={String(artifact.artifact_id)} style={{ border: '1px solid #444', borderRadius: 6, padding: 8, marginBottom: 8 }}>
              <div>{String(artifact.name)}</div>
              <div style={{ fontSize: 11, color: '#aaa' }}>{String(artifact.mime_type ?? '')} · {String(artifact.size ?? '')} bytes</div>
            </div>
          ))}
        </div>
      )}

      {tab === 'settings' && activeAgent && (
        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          <label style={{ display: 'block', marginBottom: 8 }}>
            model
            <input value={activeAgent.settings.model} onChange={(e) => onPatchSettings({ model: e.target.value })} style={{ width: '100%' }} />
          </label>
          <label style={{ display: 'block', marginBottom: 8 }}>
            base_url
            <input value={activeAgent.settings.base_url} onChange={(e) => onPatchSettings({ base_url: e.target.value })} style={{ width: '100%' }} />
          </label>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <input type="checkbox" checked={activeAgent.settings.yolo} onChange={(e) => onPatchSettings({ yolo: e.target.checked })} />
            YOLO (next approval check)
          </label>
          <label style={{ display: 'block', marginBottom: 8 }}>
            temperature
            <input type="number" step="0.1" min="0" max="2" value={activeAgent.settings.temperature}
              onChange={(e) => onPatchSettings({ temperature: Number(e.target.value) })} style={{ width: '100%' }} />
          </label>
          <div style={{ fontSize: 11, color: '#aaa' }}>Changes apply to this session on the next LLM request.</div>
        </div>
      )}
    </aside>
  );
}

export default function App() {
  const { projects, activeId, setActiveId, refresh: refreshProjects } = useProjects();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventEnvelope | null>(null);
  const [roles, setRoles] = useState<Array<{ role_id: string; display_name: string }>>([]);
  const [draft, setDraft] = useState('');
  const [newProject, setNewProject] = useState('');
  const [error, setError] = useState<string | null>(null);

  const activeProject = projects.find((p) => p.id === activeId) ?? null;
  const activeAgent = agents.find((a) => a.id === activeAgentId) ?? null;

  useEffect(() => {
    api.listRoles().then(setRoles);
  }, []);

  useEffect(() => {
    if (!activeId) return;
    setAgents([]);
    setActiveAgentId(null);
    setMessages([]);
    setEvents([]);
    api.listAgents(activeId).then((list) => {
      setAgents(list);
      if (list[0]) selectAgent(list[0].id);
    });
  }, [activeId]);

  useEffect(() => {
    if (!activeProject) return;
    const projectId = activeProject.id;
    let cursor = 0;
    const source = streamProject(projectId, cursor, (event) => {
      cursor = event.seq;
      setEvents((prev) => [...prev, event].slice(-200));
      if (event.session_id && event.session_id === activeAgentId) refreshAgent(event.session_id);
    });
    return () => source.close();
  }, [activeProject?.id, activeAgentId]);

  async function refreshAgent(agentId: string) {
    const [agent, transcript] = await Promise.all([api.getAgent(agentId), api.transcript(agentId)]);
    setAgents((prev) => prev.map((a) => (a.id === agentId ? agent : a)));
    setMessages(transcript.messages);
  }

  async function selectAgent(agentId: string) {
    setActiveAgentId(agentId);
    const [agent, transcript, eventList] = await Promise.all([
      api.getAgent(agentId),
      api.transcript(agentId),
      api.events(agentId),
    ]);
    setAgents((prev) => (prev.some((a) => a.id === agentId) ? prev.map((a) => (a.id === agentId ? agent : a)) : [...prev, agent]));
    setMessages(transcript.messages);
    setEvents(eventList);
  }

  async function createProjectAndSelect() {
    if (!newProject.trim()) return;
    const resp = await api.createProject(newProject.trim());
    await refreshProjects();
    setActiveId(resp.data.id);
    setNewProject('');
  }

  async function sendMessage() {
    if (!draft.trim() || !activeProject) return;
    try {
      if (!activeAgent) {
        const resp = await api.spawnAgent(activeProject.id, {
          role_id: 'coordinator',
          query: draft.trim(),
        });
        await selectAgent(resp.data.id);
      } else {
        await api.sendMessage(activeAgent.id, draft.trim());
        await refreshAgent(activeAgent.id);
      }
      setDraft('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function spawnRole(roleId: string) {
    if (!activeProject) return;
    const resp = await api.spawnAgent(activeProject.id, { role_id: roleId });
    await selectAgent(resp.data.id);
  }

  async function patchSettings(patch: Record<string, unknown>) {
    if (!activeAgent) return;
    const resp = await api.patchSettings(activeAgent.id, patch);
    setAgents((prev) => prev.map((a) => (a.id === activeAgent.id ? resp.data : a)));
  }

  const toolEvents = useMemo(() => events.filter((e) => e.type.startsWith('tool.') || e.type.startsWith('llm.')), [events]);

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'system-ui', background: '#111', color: '#e8e8e8' }}>
      <aside style={{ width: 220, borderRight: '1px solid #333', padding: 12, overflowY: 'auto' }}>
        <h3>Projects</h3>
        <div style={{ display: 'flex', gap: 6 }}>
          <input value={newProject} onChange={(e) => setNewProject(e.target.value)} placeholder="new project" style={{ flex: 1 }} />
          <button onClick={createProjectAndSelect}>+</button>
        </div>
        {projects.map((p) => (
          <div
            key={p.id}
            onClick={() => setActiveId(p.id)}
            style={{ padding: '8px 6px', cursor: 'pointer', background: p.id === activeId ? '#2a4a6a' : 'transparent' }}
          >
            <div style={{ fontWeight: 600 }}>{p.name}</div>
            <div style={{ fontSize: 11, color: '#aaa' }}>{p.settings.orchestration_mode}</div>
          </div>
        ))}
      </aside>

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, padding: 8, borderBottom: '1px solid #333', alignItems: 'center', overflowX: 'auto' }}>
          <span style={{ fontWeight: 700 }}>{activeProject?.name ?? 'Select a project'}</span>
          {agents.map((a) => (
            <button
              key={a.id}
              onClick={() => selectAgent(a.id)}
              style={{ background: a.id === activeAgentId ? '#2a4a6a' : '#222', border: '1px solid #444', borderRadius: 6, padding: '4px 8px', whiteSpace: 'nowrap' }}
            >
              {a.display_name} <span style={{ color: a.state === 'running' ? '#7fd07f' : '#ccc' }}>· {a.state}</span>
            </button>
          ))}
          <select value="" onChange={(e) => e.target.value && spawnRole(e.target.value)} style={{ background: '#222', color: '#eee' }}>
            <option value="">spawn…</option>
            {roles.map((r) => (
              <option key={r.role_id} value={r.role_id}>{r.display_name}</option>
            ))}
          </select>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
          {messages.map((m, i) => (
            <div key={`${m.event_id}-${i}`} style={{ marginBottom: 10, maxWidth: '85%', marginLeft: m.sender === 'user' ? 'auto' : 0 }}>
              <div style={{ background: m.sender === 'user' ? '#1f5f3a' : '#222', border: '1px solid #333', borderRadius: 10, padding: '8px 12px' }}>
                <div style={{ fontSize: 10, color: '#aaa', marginBottom: 4 }}>{m.sender ?? 'agent'}</div>
                {m.content}
              </div>
            </div>
          ))}
        </div>

        <div style={{ padding: 10, borderTop: '1px solid #333', display: 'flex', gap: 8 }}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            placeholder={activeAgent ? `guide ${activeAgent.role_id}…` : 'start a coordinator task…'}
            style={{ flex: 1, padding: 8 }}
          />
          <button onClick={sendMessage} style={{ padding: '8px 16px' }}>Send</button>
          {activeAgent && <button onClick={() => api.cancel(activeAgent.id).then((r) => setAgents((p) => p.map((a) => (a.id === r.data.id ? r.data : a))))}>Cancel</button>}
          {activeAgent && <button onClick={() => api.restart(activeAgent.id).then((r) => setAgents((p) => p.map((a) => (a.id === r.data.id ? r.data : a))))}>Restart</button>}
        </div>
        {error && <div style={{ color: '#ff8080', padding: '4px 12px' }}>{error}</div>}
      </main>

      <Inspector
        activeAgent={activeAgent}
        activeProject={activeProject}
        events={toolEvents}
        selectedEvent={selectedEvent}
        onSelectEvent={setSelectedEvent}
        onPatchSettings={patchSettings}
      />
    </div>
  );
}
