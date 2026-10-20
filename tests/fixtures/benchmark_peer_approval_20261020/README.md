# Benchmark peer approval regression

This approval payload was read from the real DeepSeek V4 Flash M3 run in
`batch_159a23ad57b64073`, source `81def568`. The root coordinator had unattended
execution enabled. Its independently spawned AgentHub peer used ordinary role
defaults, so a read-only compound Bash command entered manual approval at
2026-10-20T16:06:28Z. The headless runtime had no approval decision endpoint.
The existing background-work watcher correctly kept the task open.

The regression replays the original `normalized_arguments` through the real
Bash/tool pipeline for both CLI and Web Benchmark entry points. Only the
external model/audit decision is scripted; no new quantum calculation runs.
This fixture makes no scientific pass/fail claim about M3.

Ordinary AgentHub peers remain independent of their callers. Benchmark-wide
unattended execution belongs in the existing project defaults.
