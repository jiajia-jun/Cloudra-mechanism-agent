"""Conformer archives in the shared compute database; synchronous worker API."""
from __future__ import annotations

from cloudra.persistence.database import ComputeDB, retry_on_locked
from cloudra.tools.core.conformer_catalog import CandidateRecord


def put_candidate(db: ComputeDB, record: CandidateRecord) -> str:
    return retry_on_locked(lambda: _put_candidate(db, record))


def _put_candidate(db: ComputeDB, record: CandidateRecord) -> str:
    record = CandidateRecord.model_validate(record.model_dump())
    record.verify_artifact()
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        scope = con.execute('SELECT project_id,owner_id FROM conformer_catalogs WHERE catalog_id=?',
                            (record.catalog_id,)).fetchone()
        if scope and scope != (record.project_id, record.owner_id):
            raise ValueError('catalog project/owner mismatch')
        if record.parent_id:
            parent = con.execute('SELECT payload FROM conformer_candidates WHERE candidate_id=? AND catalog_id=?',
                                 (record.parent_id, record.catalog_id)).fetchone()
            if not parent or CandidateRecord.model_validate_json(parent[0]).species_key != record.species_key:
                raise ValueError('parent missing or belongs to different identity/catalog')
        old = con.execute('SELECT payload FROM conformer_candidates WHERE candidate_id=?',
                          (record.candidate_id,)).fetchone()
        if old:
            saved = CandidateRecord.model_validate_json(old[0])
            if saved.immutable_payload() != record.immutable_payload():
                raise ValueError('immutable candidate conflict')
            return record.candidate_id
        con.execute('INSERT OR IGNORE INTO conformer_catalogs VALUES (?,?,?)',
                    (record.catalog_id, record.project_id, record.owner_id))
        con.execute('INSERT INTO conformer_candidates VALUES (?,?,?)',
                    (record.candidate_id, record.catalog_id, record.model_dump_json()))
    return record.candidate_id


def list_candidates(db: ComputeDB, catalog_id: str, *, project_id: str, owner_id: str) -> list[CandidateRecord]:
    with db.connect() as con:
        scope = con.execute('SELECT project_id,owner_id FROM conformer_catalogs WHERE catalog_id=?',
                            (catalog_id,)).fetchone()
        if scope and scope != (project_id, owner_id):
            raise ValueError('catalog project/owner mismatch')
        rows = con.execute('SELECT payload FROM conformer_candidates WHERE catalog_id=? ORDER BY candidate_id',
                           (catalog_id,)).fetchall()
    return [CandidateRecord.model_validate_json(row[0]) for row in rows]


def put_region_snapshot(db: ComputeDB, snapshot, *, project_id: str, owner_id: str) -> None:
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            scope = con.execute('SELECT project_id,owner_id FROM conformer_catalogs WHERE catalog_id=?',
                                (snapshot.catalog_id,)).fetchone()
            if scope != (project_id, owner_id):
                raise ValueError('catalog project/owner mismatch')
            old = con.execute('SELECT payload FROM conformer_regions WHERE catalog_id=? AND revision=?',
                              (snapshot.catalog_id, snapshot.revision)).fetchone()
            if old and old[0] != snapshot.model_dump_json():
                raise ValueError('immutable snapshot conflict')
            con.execute('INSERT OR IGNORE INTO conformer_regions VALUES (?,?,?)',
                        (snapshot.catalog_id, snapshot.revision, snapshot.model_dump_json()))
    retry_on_locked(operation)


def get_region_snapshot(db: ComputeDB, catalog_id: str, revision: str, *, project_id: str, owner_id: str):
    from cloudra.tools.core.conformer_regions import RegionSnapshot

    list_candidates(db, catalog_id, project_id=project_id, owner_id=owner_id)
    with db.connect() as con:
        row = con.execute('SELECT payload FROM conformer_regions WHERE catalog_id=? AND revision=?',
                          (catalog_id, revision)).fetchone()
    if row is None:
        raise ValueError('snapshot not found')
    return RegionSnapshot.model_validate_json(row[0])
