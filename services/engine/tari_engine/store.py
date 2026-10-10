"""Local SQLite persistence for sessions, events, recommendations and metrics.

- Writes go through one background thread (batched) so the frame path never
  blocks on disk.
- On open, the database is integrity-checked. A corrupt file is moved aside
  (never deleted) and a fresh database is created; the recovery is reported.
- The player profile is computed only from persisted session measurements.
  With too few validated sessions the trend is ``insufficient_data``.
"""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tari_schema import (
    CoachingEvent, CoachingRecommendation, PerformanceSnapshot, PlayerProfile, RecurringIssue, SessionSummary,
    SkillDataPoint, SkillProgress,
)

log = logging.getLogger("tari.store")
DB_SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  player_id TEXT NOT NULL,
  started_ts REAL NOT NULL,
  ended_ts REAL,
  source_kind TEXT,
  source_label TEXT,
  environment TEXT,
  end_reason TEXT,
  frames_processed INTEGER DEFAULT 0,
  frames_dropped INTEGER DEFAULT 0,
  simulated INTEGER DEFAULT 0,
  summary_json TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  ts_ms REAL NOT NULL,
  frame_id INTEGER,
  type TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, type);
CREATE TABLE IF NOT EXISTS recommendations (
  rec_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  created_ts REAL NOT NULL,
  rule_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  priority TEXT NOT NULL,
  confidence REAL NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recs_session ON recommendations(session_id);
CREATE TABLE IF NOT EXISTS session_metrics (
  session_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  samples INTEGER NOT NULL,
  method TEXT NOT NULL,
  PRIMARY KEY (session_id, metric)
);
CREATE TABLE IF NOT EXISTS perf_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  ts_ms REAL NOT NULL,
  source TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class SkillSpec:
    key: str
    label: str
    unit: str
    better: str
    min_samples: int
    min_abs_change: float
    threshold: float
    ratio_of: str | None = None  # for count metrics: value / samples


SKILLS = [
    SkillSpec("vertical_entry_abs_offset_deg", "Head-level placement", "deg", "lower", 4, 0.1, 0.9),
    SkillSpec("horizontal_entry_abs_offset_deg", "Angle preparation", "deg", "lower", 4, 0.3, 4.0),
    SkillSpec("acquisition_time_ms", "Target acquisition", "ms", "lower", 5, 25.0, 480.0),
    SkillSpec("overshoot_flicks", "Flick control (overshoot share)", "ratio", "lower", 5, 0.1, 0.4, ratio_of="samples"),
    SkillSpec("unstable_shots", "Shot stability (shots during view motion)", "ratio", "lower", 5, 0.1, 0.35,
              ratio_of="samples"),
    SkillSpec("moving_shots", "Movement discipline (shots while moving)", "ratio", "lower", 5, 0.1, 0.35,
              ratio_of="samples"),
]


class SessionStore:
    def __init__(self, path: Path):
        self.path = path
        self.recovery: dict[str, str] | None = None
        self.degraded: str | None = None
        self._q: queue.Queue[Callable[[sqlite3.Connection], None] | None] = queue.Queue()
        self._open()
        self._thread = threading.Thread(target=self._writer, name="tari-store", daemon=True)
        self._thread.start()

    # -- lifecycle ---------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = self._connect()
            result = conn.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                raise sqlite3.DatabaseError(f"integrity check failed: {result}")
            conn.executescript(SCHEMA)
            conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
            conn.commit()
            conn.close()
        except sqlite3.DatabaseError as exc:
            quarantine = self.path.with_name(f"{self.path.stem}.corrupt-{int(time.time())}{self.path.suffix}")
            for suffix in ("", "-wal", "-shm"):
                src = Path(str(self.path) + suffix)
                if src.exists():
                    src.rename(Path(str(quarantine) + suffix))
            self.recovery = {"quarantined_to": str(quarantine), "error": str(exc)}
            log.error("database corrupt; quarantined and recreated", extra=self.recovery)
            conn = self._connect()
            conn.executescript(SCHEMA)
            conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
            conn.commit()
            conn.close()

    def _writer(self) -> None:
        conn = self._connect()
        while True:
            job = self._q.get()
            if job is None:
                self._q.task_done()
                break
            batch = [job]
            while len(batch) < 500:
                try:
                    nxt = self._q.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    self._q.put(None)
                    self._q.task_done()
                    break
                batch.append(nxt)
            try:
                for fn in batch:
                    fn(conn)
                conn.commit()
                self.degraded = None
            except sqlite3.Error as exc:
                conn.rollback()
                self.degraded = f"write failed: {exc}"
                log.error("persistence write failed", extra={"error": str(exc), "batch": len(batch)})
            finally:
                for _ in batch:
                    self._q.task_done()
        conn.close()

    def flush(self, timeout_s: float = 5.0) -> None:
        deadline = time.time() + timeout_s
        while self._q.unfinished_tasks and time.time() < deadline:
            time.sleep(0.005)

    def close(self) -> None:
        self._q.put(None)
        self._thread.join(timeout=5.0)

    def _submit(self, fn: Callable[[sqlite3.Connection], None]) -> None:
        self._q.put(fn)

    def _read(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    # -- writes ---------------------------------------------------------------------
    def start_session(self, session_id: str, player_id: str, started_ts: float, source_kind: str,
                      source_label: str, simulated: bool) -> None:
        self._submit(lambda c: c.execute(
            "INSERT OR REPLACE INTO sessions(session_id, player_id, started_ts, source_kind, source_label, simulated)"
            " VALUES (?,?,?,?,?,?)", (session_id, player_id, started_ts, source_kind, source_label, int(simulated))))

    def end_session(self, summary: SessionSummary, reason: str, environment: str, simulated: bool) -> None:
        def job(c: sqlite3.Connection) -> None:
            c.execute("UPDATE sessions SET ended_ts=?, end_reason=?, environment=?, frames_processed=?, "
                      "frames_dropped=?, simulated=MAX(simulated, ?), summary_json=? WHERE session_id=?",
                      (summary.ended_ts_ms, reason, environment, summary.frames_processed, summary.frames_dropped,
                       int(simulated), summary.model_dump_json(), summary.session_id))
            c.executemany("INSERT OR REPLACE INTO session_metrics VALUES (?,?,?,?,?,?)",
                          [(summary.session_id, m.metric, m.value, m.unit, m.samples, m.method) for m in summary.metrics])
        self._submit(job)

    def add_events(self, events: list[CoachingEvent]) -> None:
        if not events:
            return
        rows = [(e.session_id, e.ts_ms, e.frame_id, e.type, e.model_dump_json()) for e in events]
        self._submit(lambda c: c.executemany(
            "INSERT INTO events(session_id, ts_ms, frame_id, type, payload_json) VALUES (?,?,?,?,?)", rows))

    def add_recommendations(self, recs: list[CoachingRecommendation]) -> None:
        if not recs:
            return
        rows = [(r.rec_id, r.session_id, r.created_ts_ms, r.rule_id, r.domain, r.priority, r.confidence,
                 r.model_dump_json()) for r in recs]
        self._submit(lambda c: c.executemany(
            "INSERT OR REPLACE INTO recommendations VALUES (?,?,?,?,?,?,?,?)", rows))

    def add_perf_snapshot(self, session_id: str | None, snapshot: PerformanceSnapshot) -> None:
        row = (session_id, snapshot.ts_ms, snapshot.source, snapshot.model_dump_json())
        self._submit(lambda c: c.execute(
            "INSERT INTO perf_snapshots(session_id, ts_ms, source, payload_json) VALUES (?,?,?,?)", row))

    # -- reads -----------------------------------------------------------------------
    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM events e WHERE e.session_id=s.session_id AND e.type='target_exposed')"
                " AS exposures, (SELECT COUNT(*) FROM recommendations r WHERE r.session_id=s.session_id) AS recs"
                " FROM sessions s ORDER BY started_ts DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d.pop("summary_json", None)
            d["simulated"] = bool(d["simulated"])
            out.append(d)
        return out

    def session_detail(self, session_id: str) -> dict[str, Any] | None:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if row is None:
                return None
            metrics = [dict(m) for m in conn.execute(
                "SELECT metric, value, unit, samples, method FROM session_metrics WHERE session_id=?", (session_id,))]
            recs = [json.loads(r["payload_json"]) for r in conn.execute(
                "SELECT payload_json FROM recommendations WHERE session_id=? ORDER BY created_ts", (session_id,))]
            counts = {r["type"]: r["n"] for r in conn.execute(
                "SELECT type, COUNT(*) AS n FROM events WHERE session_id=? GROUP BY type", (session_id,))}
            perf = conn.execute("SELECT payload_json FROM perf_snapshots WHERE session_id=? AND source='engine' "
                                "ORDER BY ts_ms DESC LIMIT 1", (session_id,)).fetchone()
            client_perf = conn.execute("SELECT payload_json FROM perf_snapshots WHERE session_id=? AND source='desktop' "
                                       "ORDER BY ts_ms DESC LIMIT 1", (session_id,)).fetchone()
        d = dict(row)
        d["simulated"] = bool(d["simulated"])
        d["summary"] = json.loads(d.pop("summary_json")) if d.get("summary_json") else None
        d["metrics"] = metrics
        d["recommendations"] = recs
        d["event_counts"] = counts
        d["last_engine_perf"] = json.loads(perf["payload_json"]) if perf else None
        d["last_client_perf"] = json.loads(client_perf["payload_json"]) if client_perf else None
        return d

    def profile(self, player_id: str = "local", include_simulated: bool = False) -> PlayerProfile:
        with self._read() as conn:
            sessions = [dict(r) for r in conn.execute(
                "SELECT session_id, started_ts, environment, simulated FROM sessions WHERE player_id=? "
                "AND ended_ts IS NOT NULL ORDER BY started_ts", (player_id,))]
            if not include_simulated:
                sessions = [s for s in sessions if not s["simulated"]]
            ids = [s["session_id"] for s in sessions]
            metrics: dict[str, dict[str, sqlite3.Row]] = {}
            if ids:
                q = ",".join("?" * len(ids))
                for m in conn.execute(f"SELECT * FROM session_metrics WHERE session_id IN ({q})", ids):
                    metrics.setdefault(m["session_id"], {})[m["metric"]] = m
            issues = []
            if ids:
                q = ",".join("?" * len(ids))
                issues = [dict(r) for r in conn.execute(
                    f"SELECT rule_id, COUNT(DISTINCT session_id) AS sessions, COUNT(*) AS occurrences, "
                    f"MAX(created_ts) AS last_ts FROM recommendations WHERE session_id IN ({q}) AND rule_id NOT LIKE "
                    f"'%.good' GROUP BY rule_id", ids)]
            exposures = 0
            if ids:
                q = ",".join("?" * len(ids))
                exposures = conn.execute(
                    f"SELECT COUNT(*) FROM events WHERE type='target_exposed' AND session_id IN ({q})", ids).fetchone()[0]

        skills: list[SkillProgress] = []
        validated: set[str] = set()
        latest: dict[str, tuple[float, SkillSpec]] = {}
        for spec in SKILLS:
            points: list[SkillDataPoint] = []
            method = ""
            for s in sessions:
                m = metrics.get(s["session_id"], {}).get(spec.key)
                if m is None or m["samples"] < spec.min_samples:
                    continue
                value = m["value"] / m["samples"] if spec.ratio_of else m["value"]
                method = m["method"]
                points.append(SkillDataPoint(session_id=s["session_id"], ts_ms=s["started_ts"], value=round(value, 4),
                                             samples=m["samples"]))
                validated.add(s["session_id"])
            trend, detail = _trend(points, spec)
            if points:
                latest[spec.key] = (points[-1].value, spec)
            skills.append(SkillProgress(skill=spec.key, label=spec.label, unit=spec.unit, method=method or "n/a",
                                        better=spec.better, points=points, trend=trend,  # type: ignore[arg-type]
                                        trend_detail=detail))
        focus, reason = None, None
        worst = None
        for key, (value, spec) in latest.items():
            ratio = value / spec.threshold if spec.threshold else 0.0
            if ratio > 1.0 and (worst is None or ratio > worst[0]):
                worst = (ratio, spec, value)
        if worst is not None:
            _, spec, value = worst
            focus = spec.key
            reason = (f"{spec.label}: latest validated session measured {value:.2f} {spec.unit} "
                      f"against a target of {spec.threshold:.2f} {spec.unit}.")
        envs: dict[str, int] = {}
        for s in sessions:
            envs[s["environment"] or "unknown"] = envs.get(s["environment"] or "unknown", 0) + 1
        return PlayerProfile(
            player_id=player_id, generated_ts_ms=time.time() * 1000.0, sessions_total=len(sessions),
            validated_sessions=len(validated), total_exposures=int(exposures), skills=skills,
            recurring_issues=[RecurringIssue(rule_id=i["rule_id"], sessions=i["sessions"], occurrences=i["occurrences"],
                                             last_ts_ms=i["last_ts"]) for i in issues if i["sessions"] >= 2],
            environments=envs, next_focus=focus, next_focus_reason=reason,
        )


def _trend(points: list[SkillDataPoint], spec: SkillSpec) -> tuple[str, str | None]:
    """Trend from persisted, validated session values only.

    >= 6 sessions: mean of the last 3 vs the mean of the 3 before them.
    3-5 sessions: the latest session vs the first of the last three.
    """
    n = len(points)
    if n < 3:
        return "insufficient_data", f"{n} validated session(s); at least 3 are needed for a trend."
    if n >= 6:
        r = statistics.fmean(p.value for p in points[-3:])
        p = statistics.fmean(p.value for p in points[-6:-3])
        detail = f"Last 3 validated sessions average {r:.2f} {spec.unit} vs {p:.2f} {spec.unit} in the 3 before."
    else:
        r, p = points[-1].value, points[-3].value
        detail = f"Latest validated session {r:.2f} {spec.unit} vs {p:.2f} {spec.unit} two sessions earlier."
    delta = r - p
    rel = abs(delta) / max(abs(p), 1e-9)
    if abs(delta) < spec.min_abs_change or rel < 0.1:
        return "stable", detail
    improving = delta < 0 if spec.better == "lower" else delta > 0
    return ("improving" if improving else "declining"), detail
