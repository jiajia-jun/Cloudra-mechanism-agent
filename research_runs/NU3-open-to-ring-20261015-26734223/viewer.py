"""Read-only UI over temporary database snapshots; no runtime lifespan."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time

RUN = Path(__file__).resolve().parent
SNAPSHOT = Path('/private/tmp/cloudra-open-to-ring-26734223-viewer')
os.environ['CLOUDRA_CONFIG_FILE'] = str(SNAPSHOT / 'unused-config.yaml')
os.environ['CLOUDRA_DATA_DIR'] = str(SNAPSHOT)
os.environ['CLOUDRA_API_TOKEN'] = 'off'
os.environ['CLOUDRA_API_BIND_HOST'] = '127.0.0.1'
os.environ['CLOUDRA_DAEMON_WATCHDOG'] = 'off'

from cloudra.persistence.paths import compute_db_path, conversation_db_path, runtime_db_path
from cloudra.runtime_v2.apply import _APPLIERS, apply_event
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.services.api_v2.app import create_v2_app
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

FRONTEND = Path('/Users/cloudrayyy/.codex/worktrees/tool-document-loading/Cloudra-mechanism-agent-master/frontend/dist')


def backup(source, target):
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as reader:
        with closing(sqlite3.connect(target)) as writer:
            reader.backup(writer)


def snapshot_app():
    launch = json.loads((RUN / 'launch.json').read_text())
    runtime = RUN / 'runtime'
    # All API database reads resolve to these disposable copies, including DAG/compute.
    for source, target in (
        (runtime_db_path(runtime), runtime_db_path(SNAPSHOT)),
        (compute_db_path(runtime), compute_db_path(SNAPSHOT)),
        (conversation_db_path(launch['project_id'], runtime),
         conversation_db_path(launch['project_id'], SNAPSHOT)),
    ):
        backup(source, target)
    core = RuntimeCore(strict_events=True)
    store = RuntimeStore(str(runtime_db_path(SNAPSHOT)))
    core.store = store
    # Replay facts only: restore_core would apply interrupted-run recovery.
    core.event_log.restore_from_store(store)
    for envelope in store.iter_events(types=_APPLIERS):
        apply_event(core, envelope)
    core.event_writer.mark_restored()
    core.notices.restore_from(core.event_log)
    app = create_v2_app(core)
    app.mount('/', StaticFiles(directory=str(FRONTEND), html=True), name='frontend')
    return app


class ReadOnlyViewer:
    def __init__(self):
        self.app = snapshot_app()
        self.updated_at = time.monotonic()
        self.lock = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        if scope['type'] == 'http' and scope['method'] not in ('GET', 'HEAD', 'OPTIONS'):
            await JSONResponse({'detail': 'Read-only research observer.'}, status_code=403)(scope, receive, send)
            return
        if scope['type'] == 'http' and time.monotonic() - self.updated_at >= 5:
            async with self.lock:
                if time.monotonic() - self.updated_at >= 5:
                    self.app = await asyncio.to_thread(snapshot_app)
                    self.updated_at = time.monotonic()
        await self.app(scope, receive, send)


if __name__ == '__main__':
    uvicorn.run(ReadOnlyViewer(), host='127.0.0.1', port=8015,
                lifespan='off', log_level='warning')
