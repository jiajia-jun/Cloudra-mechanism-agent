CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    stream TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT,
    run_id TEXT,
    seq INTEGER NOT NULL,
    session_seq INTEGER,
    type TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE objects (
    kind TEXT NOT NULL,
    obj_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (kind, obj_id)
);
