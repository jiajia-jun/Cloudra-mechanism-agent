CREATE INDEX idx_ent_tags_tag ON kg_entity_tags(facet, tag);

CREATE INDEX idx_rel_dst ON kg_relations(dst_id);

CREATE INDEX idx_rel_source ON kg_relations(source);

CREATE INDEX idx_rel_src ON kg_relations(src_id);

CREATE TABLE kg_entities(
      id TEXT PRIMARY KEY, type TEXT NOT NULL, label TEXT NOT NULL, smiles TEXT,
      props TEXT, n_sources INTEGER NOT NULL DEFAULT 1, created_at TEXT, updated_at TEXT);

CREATE VIRTUAL TABLE kg_entities_fts USING fts5(
      label, smiles, props, content='kg_entities', content_rowid='rowid', tokenize='trigram');

CREATE TABLE 'kg_entities_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;

CREATE TABLE 'kg_entities_fts_data'(id INTEGER PRIMARY KEY, block BLOB);

CREATE TABLE 'kg_entities_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);

CREATE TABLE 'kg_entities_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;

CREATE TABLE kg_entity_tags(
      entity_id TEXT NOT NULL REFERENCES kg_entities(id),
      facet TEXT NOT NULL, tag TEXT NOT NULL,
      PRIMARY KEY(entity_id, facet, tag)) WITHOUT ROWID
    ;

CREATE TABLE kg_relations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      src_id TEXT NOT NULL REFERENCES kg_entities(id), dst_id TEXT NOT NULL REFERENCES kg_entities(id),
      rel_type TEXT NOT NULL, evidence_level TEXT NOT NULL DEFAULT 'L0', source TEXT NOT NULL,
      falsified INTEGER NOT NULL DEFAULT 0, note TEXT DEFAULT '', created_at TEXT,
      UNIQUE(src_id, dst_id, rel_type, source));

CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY);

CREATE TABLE sqlite_sequence(name,seq);

CREATE TRIGGER kg_entities_ad AFTER DELETE ON kg_entities BEGIN
      INSERT INTO kg_entities_fts(kg_entities_fts, rowid, label, smiles, props)
      VALUES ('delete', old.rowid, old.label, old.smiles, old.props);
    END;

CREATE TRIGGER kg_entities_ai AFTER INSERT ON kg_entities BEGIN
      INSERT INTO kg_entities_fts(rowid, label, smiles, props)
      VALUES (new.rowid, new.label, new.smiles, new.props);
    END;

CREATE TRIGGER kg_entities_au AFTER UPDATE ON kg_entities BEGIN
      INSERT INTO kg_entities_fts(kg_entities_fts, rowid, label, smiles, props)
      VALUES ('delete', old.rowid, old.label, old.smiles, old.props);
      INSERT INTO kg_entities_fts(rowid, label, smiles, props)
      VALUES (new.rowid, new.label, new.smiles, new.props);
    END;
