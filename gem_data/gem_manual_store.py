"""Isolated GEM-only append-only storage for *user-entered* manual events.

Disabled unless GEM_MANUAL_PERSIST_ENABLED=yes and a separate restricted
Postgres role is supplied. No broker connectivity. Every append is serialized,
validated against replayed cash/shares, and hash-chain checked.
"""
from __future__ import annotations

import json
import os
from hashlib import sha256

import psycopg

from gem_data.gem_manual_ops import replay_manual_events, ManualLedgerHold

EXPERIMENT = "gem-v1-forward-2026-10"
_ADVISORY_LOCK_KEY = 90210713001


class ManualPersistenceHold(ValueError):
    pass


def _hash(payload):
    return sha256(json.dumps(payload, sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _config():
    url=os.getenv("GEM_MANUAL_WRITER_DATABASE_URL","").strip()
    if (os.getenv("GEM_MANUAL_PERSIST_ENABLED")!="yes"
            or not url.startswith("postgresql://gem_manual_append_limited:")):
        raise ManualPersistenceHold("GEM manual database persistence is disabled")
    return url


def _lock(cur):
    cur.execute("SET TRANSACTION READ WRITE")
    cur.execute("SET LOCAL statement_timeout = 10000")
    cur.execute("SELECT pg_advisory_xact_lock(%s)",(_ADVISORY_LOCK_KEY,))


def _read_verified(cur):
    cur.execute(
        "SELECT entry_id,payload,prior_sha256,payload_sha256 FROM gem_manual_entry "
        "WHERE experiment_id=%s ORDER BY event_order ASC",
        (EXPERIMENT,))
    rows=cur.fetchall()
    if len(rows)>20000:
        raise ManualPersistenceHold("Manual ledger exceeds bounded replay limit")
    events=[]
    head="0"*64
    seen=set()
    for eid,payload,prior,digest in rows:
        if eid in seen or not isinstance(payload,dict) or payload.get("event_id")!=eid:
            raise ManualPersistenceHold("Manual event identity corruption")
        seen.add(eid)
        expected=_hash({"prev":head,"event":payload})
        if prior!=head or digest!=expected:
            raise ManualPersistenceHold("Manual ledger hash-chain integrity HOLD")
        head=digest
        events.append(payload)
    state=replay_manual_events("0",events)
    if state["head"]!=head:
        raise ManualPersistenceHold("Manual replay/DB head mismatch")
    return events,state


def _latest_statement(cur, state, events):
    cur.execute(
        "SELECT statement_payload,ledger_head_sha256,reconciliation "
        "FROM gem_manual_statement WHERE experiment_id=%s "
        "ORDER BY created_at DESC,statement_id DESC LIMIT 1",(EXPERIMENT,))
    row=cur.fetchone()
    if not row:
        return {**state,"persisted":True,"statement_status":"NO_STATEMENT_ENTERED"}
    statement,stored_head,classification=row
    if stored_head!=state["head"]:
        return {**state,"persisted":True,"statement_status":"STALE_MANUAL_STATEMENT"}
    verified=replay_manual_events("0",events,statement)
    if verified["statement_status"] != classification:
        raise ManualPersistenceHold("Imported statement classification integrity HOLD")
    return {**verified,"persisted":True}


def read_manual_account():
    url=_config()
    try:
        with psycopg.connect(url,connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout = 10000")
                events,state=_read_verified(cur)
                return _latest_statement(cur,state,events)
    except psycopg.Error as exc:
        raise ManualPersistenceHold("Isolated manual ledger database unavailable") from None


def append_manual_event(event, *, confirmation):
    if confirmation!="I_CONFIRM_THIS_MANUAL_ENTRY":
        raise ManualPersistenceHold("Explicit manual event confirmation missing")
    if not isinstance(event,dict) or not isinstance(event.get("event_id"),str):
        raise ManualPersistenceHold("Malformed manual event")
    url=_config()
    try:
        with psycopg.connect(url,connect_timeout=5) as conn:
            with conn.cursor() as cur:
                _lock(cur)
                events,state=_read_verified(cur)
                old=next((row for row in events if row["event_id"]==event["event_id"]),None)
                if old is not None:
                    if old!=event:
                        raise ManualPersistenceHold("Conflicting duplicate event id HOLD")
                    return {**_latest_statement(cur,state,events),"append_status":"IDEMPOTENT_DUPLICATE"}
                new_state=replay_manual_events("0",events+[event])
                digest=_hash({"prev":state["head"],"event":event})
                if digest!=new_state["head"]:
                    raise ManualPersistenceHold("New manual event hash mismatch")
                cur.execute(
                    "INSERT INTO gem_manual_entry "
                    "(entry_id,experiment_id,event_kind,trade_date,payload_sha256,prior_sha256,payload) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (event["event_id"],EXPERIMENT,event["type"],event["trade_date"],
                     digest,state["head"],json.dumps(event,allow_nan=False)))
                return {**new_state,"persisted":True,"append_status":"RECORDED_USER_ENTRY"}
    except psycopg.Error:
        raise ManualPersistenceHold("Isolated manual ledger append failed") from None


def append_manual_statement(statement_id, statement, *, confirmation):
    if confirmation!="I_IMPORTED_MY_BROKER_STATEMENT":
        raise ManualPersistenceHold("Explicit statement-import confirmation missing")
    if not isinstance(statement_id,str) or not 1<=len(statement_id)<=120:
        raise ManualPersistenceHold("Missing statement receipt id")
    if not isinstance(statement,dict):
        raise ManualPersistenceHold("Malformed imported broker statement")
    url=_config()
    try:
        with psycopg.connect(url,connect_timeout=5) as conn:
            with conn.cursor() as cur:
                _lock(cur)
                events,state=_read_verified(cur)
                classified=replay_manual_events("0",events,statement)
                cur.execute("SELECT statement_payload,ledger_head_sha256 "
                            "FROM gem_manual_statement WHERE statement_id=%s AND experiment_id=%s",
                            (statement_id,EXPERIMENT))
                previous=cur.fetchone()
                if previous:
                    if previous[0]!=statement or previous[1]!=state["head"]:
                        raise ManualPersistenceHold("Conflicting statement id HOLD")
                    return {**classified,"persisted":True,"append_status":"IDEMPOTENT_DUPLICATE"}
                cur.execute(
                    "INSERT INTO gem_manual_statement "
                    "(statement_id,experiment_id,statement_as_of,source_sha256,"
                    "ledger_head_sha256,statement_payload,reconciliation) "
                    "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)",
                    (statement_id,EXPERIMENT,statement["as_of"],
                     statement["statement_sha256"],state["head"],
                     json.dumps(statement,allow_nan=False),
                     classified["statement_status"]))
                return {**classified,"persisted":True,"append_status":"IMPORTED_USER_STATEMENT"}
    except psycopg.Error:
        raise ManualPersistenceHold("Isolated manual statement import failed") from None
