CREATE INDEX idx_artifacts_session
    ON artifacts(session_id, created_at)
;

CREATE INDEX idx_dag_call_reviews_compute_job
    ON dag_call_reviews(compute_job_id)
;

CREATE INDEX idx_dag_call_reviews_tool_call
    ON dag_call_reviews(tool_call_id)
;

CREATE INDEX idx_dag_evidence_compute_job
    ON dag_evidence(compute_job_id)
;

CREATE INDEX idx_dag_evidence_tool_call
    ON dag_evidence(tool_call_id)
;

CREATE TABLE artifact_download_tokens(
        token_hash TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

CREATE TABLE artifacts(
        artifact_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        name TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        size INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        storage_path TEXT NOT NULL,
        source_path TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );

CREATE TABLE dag_call_reviews(
        review_id TEXT PRIMARY KEY,
        tool_call_id TEXT NOT NULL DEFAULT '',
        tool_name TEXT NOT NULL,
        is_success INTEGER NOT NULL DEFAULT 0,
        caller_session_id TEXT NOT NULL DEFAULT '',
        caller_role_id TEXT NOT NULL DEFAULT '',
        caller_legacy_id TEXT NOT NULL DEFAULT '',
        arguments_digest TEXT NOT NULL DEFAULT '',
        result_summary TEXT NOT NULL DEFAULT '',
        source_path TEXT NOT NULL DEFAULT '',
        result_kind TEXT NOT NULL DEFAULT '',
        compute_job_id TEXT,
        suggested_target_id TEXT,
        suggested_stage TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT 'pending'
            CHECK(state IN ('pending', 'reviewed', 'ignored')),
        created_at TEXT NOT NULL
    , claim TEXT NOT NULL DEFAULT '', rationale TEXT NOT NULL DEFAULT '', submitter TEXT NOT NULL DEFAULT '', evidence_id TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'legacy_auto');

CREATE TABLE dag_coverage(
        graph_id TEXT PRIMARY KEY,
        revision INTEGER NOT NULL DEFAULT 0,
        coverage TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL,
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    );

CREATE TABLE dag_delivery_dispositions(
        disposition_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        disposition TEXT NOT NULL CHECK(disposition IN ('complete', 'partial', 'user_terminated')),
        graph_revision INTEGER NOT NULL,
        report TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

CREATE TABLE dag_drafts(
        draft_id TEXT PRIMARY KEY,
        state TEXT NOT NULL DEFAULT 'open'
            CHECK(state IN ('open', 'accepted', 'rejected')),
        rationale TEXT NOT NULL DEFAULT '',
        operations TEXT NOT NULL,
        stage_contracts TEXT NOT NULL DEFAULT '{}',
        actor_id TEXT NOT NULL DEFAULT '',
        reject_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        decided_at TEXT
    , claim_spec TEXT NOT NULL DEFAULT '');

CREATE TABLE dag_edges(
        graph_id TEXT NOT NULL,
        edge_id TEXT NOT NULL,
        source_node_id TEXT NOT NULL,
        target_node_id TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        refs TEXT NOT NULL DEFAULT '[]',
        payload TEXT NOT NULL DEFAULT '{}',
        stages TEXT NOT NULL DEFAULT '[]',
        created_revision INTEGER NOT NULL,
        updated_revision INTEGER NOT NULL,
        PRIMARY KEY(graph_id, edge_id),
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    );

CREATE TABLE dag_evidence(
        evidence_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_name TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL, tool_call_id TEXT, compute_job_id TEXT,
        UNIQUE(source_type, source_name, content_hash)
    );

CREATE TABLE dag_evidence_bindings(
        graph_id TEXT NOT NULL,
        target_type TEXT NOT NULL CHECK(target_type IN ('node', 'edge')),
        target_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        evidence_role TEXT,
        derived_level TEXT,
        created_revision INTEGER NOT NULL,
        PRIMARY KEY(graph_id, target_type, target_id, evidence_id),
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    );

CREATE TABLE dag_evidence_facts(
        fact_id TEXT PRIMARY KEY,
        check_name TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK(outcome IN ('supports', 'refutes', 'inconclusive')),
        subject TEXT NOT NULL DEFAULT '{}',
        source_refs TEXT NOT NULL DEFAULT '[]',
        details TEXT NOT NULL DEFAULT '{}',
        adapter_version TEXT NOT NULL,
        dedup_key TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(dedup_key)
    );

CREATE TABLE dag_graphs(
        graph_id TEXT PRIMARY KEY,
        graph_kind TEXT NOT NULL UNIQUE CHECK(graph_kind IN ('process', 'delivery')),
        revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

CREATE TABLE dag_links(
        link_id TEXT PRIMARY KEY,
        process_node_id TEXT NOT NULL,
        delivery_element_type TEXT NOT NULL CHECK(delivery_element_type IN ('node', 'edge')),
        delivery_element_id TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}',
        created_revision INTEGER NOT NULL
    );

CREATE TABLE dag_mutations(
        mutation_id TEXT PRIMARY KEY,
        graph_id TEXT NOT NULL,
        base_revision INTEGER NOT NULL,
        resulting_revision INTEGER NOT NULL,
        actor_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        session_id TEXT NOT NULL DEFAULT '',
        rationale TEXT NOT NULL DEFAULT '',
        base_revisions TEXT NOT NULL DEFAULT '{}',
        resulting_revisions TEXT NOT NULL DEFAULT '{}',
        operations TEXT NOT NULL,
        accepted INTEGER NOT NULL DEFAULT 1,
        rejection_code TEXT,
        rejection_reason TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    );

CREATE TABLE dag_nodes(
        graph_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        node_type TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        refs TEXT NOT NULL DEFAULT '[]',
        payload TEXT NOT NULL DEFAULT '{}',
        stages TEXT NOT NULL DEFAULT '[]',
        created_revision INTEGER NOT NULL,
        updated_revision INTEGER NOT NULL,
        PRIMARY KEY(graph_id, node_id),
        FOREIGN KEY(graph_id) REFERENCES dag_graphs(graph_id)
    );

CREATE TABLE dag_review_decisions(
        decision_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL,
        basis_fingerprint TEXT NOT NULL,
        verdict TEXT NOT NULL CHECK(verdict IN ('accept', 'reject', 'needs_evidence')),
        reason TEXT NOT NULL,
        evidence_refs TEXT NOT NULL DEFAULT '[]',
        findings TEXT NOT NULL DEFAULT '[]',
        next_action TEXT,
        claim_token INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

CREATE TABLE dag_review_notifications(
        notification_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL DEFAULT 'review_decision'
            CHECK(kind IN ('review_decision', 'call_verdict', 'draft_verdict')),
        decision_id TEXT NOT NULL,
        request_id TEXT NOT NULL DEFAULT '',
        recipient_session_id TEXT NOT NULL DEFAULT '',
        payload TEXT NOT NULL DEFAULT '{}',
        state TEXT NOT NULL DEFAULT 'pending'
            CHECK(state IN ('pending', 'sent')),
        created_at TEXT NOT NULL
    );

CREATE TABLE dag_review_requests(
        request_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK(kind IN ('draft', 'evidence', 'exception', 'exit')),
        requester TEXT NOT NULL,
        target_ids TEXT NOT NULL DEFAULT '[]',
        question TEXT NOT NULL,
        supporting_refs TEXT NOT NULL DEFAULT '[]',
        counterevidence_refs TEXT NOT NULL DEFAULT '[]',
        proposal TEXT NOT NULL DEFAULT '{}',
        basis_fingerprint TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'queued'
            CHECK(state IN ('queued', 'resolved', 'superseded')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    , owner TEXT, claim_token INTEGER NOT NULL DEFAULT 0, lease_expires_at TEXT);

CREATE TABLE dag_species(
        species_id TEXT PRIMARY KEY,
        canonical_key TEXT NOT NULL UNIQUE,
        charge INTEGER NOT NULL,
        multiplicity INTEGER NOT NULL CHECK(multiplicity >= 1),
        identifiers TEXT NOT NULL DEFAULT '{}',
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );

CREATE TABLE schema_migrations(
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );

CREATE TABLE session (
        session_id TEXT PRIMARY KEY,
        agent_id TEXT,
        agent_type TEXT,
        parent_session_id TEXT,
        query TEXT,
        state TEXT NOT NULL DEFAULT 'queued',
        result TEXT,
        error TEXT,
        pid INTEGER,
        worker_id TEXT,
        created_at TEXT,
        started_at TEXT,
        heartbeat_at TEXT,
        finished_at TEXT,
        exit_code INTEGER,
        node_id TEXT,
        workspace_id TEXT,
        working_directory TEXT,
        orchestration_mode TEXT NOT NULL DEFAULT 'standard',
        orchestration_config TEXT NOT NULL DEFAULT '{}'
    );

CREATE TABLE session_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        data TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );

CREATE TABLE sqlite_sequence(name,seq);
