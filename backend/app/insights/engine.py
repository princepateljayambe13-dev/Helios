"""HELIOS Insights Engine: synthesizes multi-signal surveillance telemetry into prioritized actionable insights."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.insights.ai_explainer import AiExplainer
from app.insights.baseline import BaselineEngine
from app.insights.evidence_analyzer import EvidenceAnalyzer
from app.insights.models import Insight
from app.insights.scoring import calculate_insight_score, get_priority


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class InsightsEngine:
    """Core intelligence engine for detecting, scoring, and explaining surveillance patterns."""

    def __init__(self, db: sqlite3.Connection, ollama_url: str = "http://127.0.0.1:11434"):
        self.db = db
        self.explainer = AiExplainer(base_url=ollama_url)
        self.baseline_engine = BaselineEngine(db)
        self.evidence_analyzer = EvidenceAnalyzer(db)

    def evaluate_telemetry(self) -> list[dict[str, Any]]:
        """Periodic or triggered evaluation of system telemetry to identify new/updated insights."""
        new_insights: list[dict[str, Any]] = []
        now_str = now_iso()
        cutoff_5m = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

        # 1. Evaluate Monitored Zones for Density Surges and Dwell Anomalies
        zones = self.db.execute("SELECT zone_id, name, camera_id, capacity FROM zones WHERE enabled=1").fetchall()

        for z in zones:
            zid = z["zone_id"]
            zname = z["name"] or zid
            cam_id = z["camera_id"]
            cap = max(1, int(z["capacity"] or 10))

            # Active observations in this zone
            obs = self.db.execute(
                "SELECT * FROM observations WHERE zone_id=? AND last_seen >= ?",
                (zid, cutoff_5m),
            ).fetchall()

            people = [o for o in obs if o["object_type"].upper() == "HUMAN"]
            current_people_cnt = len(people)
            dwells = [float(o["dwell_seconds"] or 0.0) for o in people]
            max_dwell = max(dwells) if dwells else 0.0
            avg_dwell = sum(dwells) / len(dwells) if dwells else 0.0

            baseline = self.baseline_engine.get_zone_baseline(zid)
            norm_people = baseline["normal_people_count"]

            # Check if Density Surge
            if current_people_cnt >= max(4, cap * 0.8) and current_people_cnt > norm_people:
                ins = self._process_zone_density_insight(
                    zone_id=zid,
                    zone_name=zname,
                    camera_id=cam_id,
                    current_count=current_people_cnt,
                    normal_count=norm_people,
                    capacity=cap,
                    avg_dwell=avg_dwell,
                    active_obs=people,
                )
                if ins:
                    new_insights.append(ins)

            # Check if Unusual Dwell
            if max_dwell >= 90.0:  # over 1.5 minutes
                ins = self._process_dwell_insight(
                    zone_id=zid,
                    zone_name=zname,
                    camera_id=cam_id,
                    max_dwell=max_dwell,
                    active_obs=people,
                )
                if ins:
                    new_insights.append(ins)

        # 2. Evaluate Cross-Camera Correlation (tracks traversing multiple cameras)
        recent_obs = self.db.execute(
            """SELECT o.* FROM observations o
               WHERE o.last_seen >= ? AND o.related_cameras IS NOT NULL""",
            (cutoff_5m,),
        ).fetchall()

        for ro in recent_obs:
            try:
                rel_cams = json.loads(ro["related_cameras"]) if ro["related_cameras"] else []
                if len(rel_cams) >= 2:
                    ins = self._process_cross_camera_insight(ro, rel_cams)
                    if ins:
                        new_insights.append(ins)
            except Exception:
                pass

        # 3. Evaluate Camera Visibility & Obstruction Degeneracies
        try:
            degraded_cams = self.db.execute(
                """SELECT c.camera_id, c.name, r.reliability_score, r.condition, r.condition_confidence, r.condition_started_at, r.condition_details
                   FROM cameras c
                   JOIN camera_reliability r ON c.camera_id = r.camera_id
                   WHERE c.enabled=1 AND r.condition != 'CLEAR' AND r.reliability_score <= 75"""
            ).fetchall()

            for dcam in degraded_cams:
                ins = self._process_camera_obstruction_insight(dcam)
                if ins:
                    new_insights.append(ins)
        except Exception:
            pass

        return new_insights

    def _process_camera_obstruction_insight(self, cam_row: Any) -> dict[str, Any] | None:
        """Create or update a CAMERA_DEGRADED insight for sustained visual degradation."""
        cam_id = cam_row["camera_id"]
        condition = cam_row["condition"]
        reliability = cam_row["reliability_score"] if cam_row["reliability_score"] is not None else 100
        confidence = cam_row["condition_confidence"] or 0.85
        cam_name = cam_row["name"] or cam_id

        # Deduplication: active insight within last 15 minutes for this camera and condition
        existing = self.db.execute(
            """SELECT * FROM insights
               WHERE camera_ids LIKE ? AND type='CAMERA_DEGRADED' AND status IN ('ACTIVE', 'DETECTED')
               ORDER BY created_at DESC LIMIT 1""",
            (f"%{cam_id}%",),
        ).fetchone()

        now_str = now_iso()
        details = {}
        if cam_row["condition_details"]:
            try: details = json.loads(cam_row["condition_details"])
            except Exception: pass
        reason = details.get("reason", f"Camera {cam_name} visual feed degraded ({condition})")

        anomaly = max(10.0, 100.0 - reliability)
        persistence = 80.0
        score, breakdown = calculate_insight_score(
            anomaly=anomaly,
            persistence=persistence,
            spatial_significance=70.0 if condition in ("DEAD_FEED", "OBSTRUCTED") else 40.0,
            cross_camera_correlation=10.0,
            density_activity_change=10.0,
            incident_relevance=60.0 if condition in ("DEAD_FEED", "OBSTRUCTED") else 30.0,
            camera_reliability=float(reliability),
        )

        prev_priority = existing["priority"] if existing else None
        priority = get_priority(score, prev_priority)

        signals = {
            "camera_id": cam_id,
            "condition": condition,
            "reliability_score": reliability,
            "reason": reason,
            "metrics": details.get("metrics", {}),
            "score_breakdown": breakdown,
        }

        summary = f"Camera {cam_name} visual degradation: {condition.replace('_', ' ').title()} (Reliability: {reliability}/100, Confidence: {int(confidence*100)}%)"

        if existing:
            ins_id = existing["insight_id"]
            self.db.execute(
                """UPDATE insights
                   SET summary=?, score=?, confidence=?, priority=?, signals=?, updated_at=?
                   WHERE insight_id=?""",
                (summary, score, confidence, priority, json.dumps(signals), now_str, ins_id),
            )
        else:
            ins_id = f"INS-{uuid.uuid4().hex[:12].upper()}"
            self.db.execute(
                """INSERT INTO insights
                   (insight_id, timestamp, type, summary, score, confidence, priority, camera_ids, zone_ids, track_ids, event_ids, evidence_ids, signals, baseline_comparison, reasoning_factors, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)""",
                (
                    ins_id,
                    now_str,
                    "CAMERA_DEGRADED",
                    summary,
                    score,
                    confidence,
                    priority,
                    json.dumps([cam_id]),
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps(signals),
                    json.dumps({"nominal_reliability": 100, "current_reliability": reliability}),
                    json.dumps([reason]),
                    now_str,
                    now_str,
                ),
            )

        self.db.commit()
        return self.get_insight(ins_id)


    def _process_zone_density_insight(
        self,
        zone_id: str,
        zone_name: str,
        camera_id: str,
        current_count: int,
        normal_count: int,
        capacity: int,
        avg_dwell: float,
        active_obs: list[Any],
    ) -> dict[str, Any] | None:
        """Create or update a DENSITY_CHANGE / CROWD_SURGE insight with deduplication."""
        # De-duplication check: active insight within last 15 minutes for this zone
        existing = self.db.execute(
            """SELECT * FROM insights
               WHERE zone_ids LIKE ? AND type='DENSITY_CHANGE' AND status IN ('ACTIVE', 'DETECTED')
               ORDER BY created_at DESC LIMIT 1""",
            (f"%{zone_id}%",),
        ).fetchone()

        now_str = now_iso()
        track_ids = [o["track_id"] for o in active_obs[:5]]
        event_ids: list[str] = []
        evidence_ids: list[str] = []
        for o in active_obs:
            try:
                evs = json.loads(o["event_ids"]) if o["event_ids"] else []
                event_ids.extend(evs)
                evds = json.loads(o["evidence_ids"]) if o["evidence_ids"] else []
                evidence_ids.extend(evds)
            except Exception:
                pass

        anomaly_score = min(100.0, (current_count / capacity) * 100.0)
        persistence = min(100.0, (avg_dwell / 60.0) * 80.0)
        density_change = min(100.0, ((current_count - normal_count) / max(1, normal_count)) * 70.0)

        score, breakdown = calculate_insight_score(
            anomaly=anomaly_score,
            persistence=persistence,
            spatial_significance=85.0 if current_count > capacity else 65.0,
            cross_camera_correlation=20.0,
            density_activity_change=density_change,
            incident_relevance=50.0 if current_count > capacity else 20.0,
            camera_reliability=100.0,
        )

        prev_priority = existing["priority"] if existing else None
        priority = get_priority(score, prev_priority)

        # Extract movement, walking, and evidence color telemetry
        evidence_intel = self.evidence_analyzer.analyze_for_insight(
            insight_type="DENSITY_CHANGE",
            active_obs=active_obs,
            evidence_ids=evidence_ids,
            track_ids=track_ids,
        )

        signals = {
            "people_count": current_count,
            "people_delta": f"{normal_count} → {current_count}",
            "capacity": capacity,
            "duration_seconds": round(avg_dwell, 1),
            "score_breakdown": breakdown,
            "movement_intel": evidence_intel.get("movement_items", []),
            "color_intel": evidence_intel.get("color_items", []),
            "evidence_snapshots": evidence_intel.get("snapshots", []),
            "movement_summary": evidence_intel.get("movement_summary"),
            "color_summary": evidence_intel.get("color_summary"),
            "walking_count": evidence_intel.get("walking_count", 0),
            "primary_color": evidence_intel.get("primary_color_label"),
            "primary_direction": evidence_intel.get("primary_direction"),
        }
        baseline = {
            "normal_people": normal_count,
            "normal_activity": 30,
        }

        # Check if CRITICAL: prompt Qwen model for in-depth synthesis
        if priority == "CRITICAL":
            qwen_res = self.explainer.summarize_critical_insight(
                insight_type="DENSITY_CHANGE",
                signals=signals,
                baseline=baseline,
                cameras=[camera_id],
                zones=[zone_name],
                evidence_intel=evidence_intel,
            )
            summary = qwen_res["summary"]
            confidence = qwen_res["confidence"]
            factors = qwen_res["reasoning_factors"]
            signals["qwen_analysis"] = qwen_res
        else:
            explanation = self.explainer.explain_insight(
                insight_type="DENSITY_CHANGE",
                signals=signals,
                baseline=baseline,
                cameras=[camera_id],
                zones=[zone_name],
                evidence_ids=evidence_ids,
            )
            summary = explanation["summary"]
            confidence = explanation["confidence"]
            factors = [
                f"Movement: {evidence_intel.get('movement_summary')}",
                f"Attire: {evidence_intel.get('color_summary')}",
                *explanation["reasoning_factors"],
            ]

        if existing:
            # Update continuing situation
            update_sql = """UPDATE insights SET
                score=?, priority=?, signals=?, track_ids=?, event_ids=?, evidence_ids=?, updated_at=?
            """
            update_params = [
                score,
                priority,
                json.dumps(signals),
                json.dumps(track_ids),
                json.dumps(list(set(event_ids))),
                json.dumps(list(set(evidence_ids))),
                now_str,
            ]
            if priority == "CRITICAL":
                update_sql += ", summary=?, reasoning_factors=?"
                update_params.extend([summary, json.dumps(factors)])

            update_sql += " WHERE insight_id=?"
            update_params.append(existing["insight_id"])
            self.db.execute(update_sql, tuple(update_params))
            self.db.commit()
            return self.get_insight(existing["insight_id"])

        insight_id = f"INS-{uuid.uuid4().hex[:6].upper()}"
        self.db.execute(
            """INSERT INTO insights (
                insight_id, timestamp, type, summary, score, confidence, priority,
                camera_ids, zone_ids, track_ids, event_ids, evidence_ids,
                signals, baseline_comparison, reasoning_factors, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                insight_id,
                now_str,
                "DENSITY_CHANGE",
                summary,
                score,
                confidence,
                priority,
                json.dumps([camera_id]),
                json.dumps([zone_id]),
                json.dumps(track_ids),
                json.dumps(list(set(event_ids))),
                json.dumps(list(set(evidence_ids))),
                json.dumps(signals),
                json.dumps(baseline),
                json.dumps(factors),
                "ACTIVE",
                now_str,
                now_str,
            ),
        )
        self.db.commit()
        return self.get_insight(insight_id)

    def _process_dwell_insight(
        self,
        zone_id: str,
        zone_name: str,
        camera_id: str,
        max_dwell: float,
        active_obs: list[Any],
    ) -> dict[str, Any] | None:
        """Create or update an UNUSUAL_DWELL insight with walking and color intelligence."""
        existing = self.db.execute(
            """SELECT * FROM insights
               WHERE zone_ids LIKE ? AND type='UNUSUAL_DWELL' AND status IN ('ACTIVE', 'DETECTED')
               ORDER BY created_at DESC LIMIT 1""",
            (f"%{zone_id}%",),
        ).fetchone()

        now_str = now_iso()
        track_ids = [o["track_id"] for o in active_obs if float(o["dwell_seconds"] or 0) >= 90.0]

        evidence_ids: list[str] = []
        event_ids: list[str] = []
        for o in active_obs:
            try:
                evs = json.loads(o["event_ids"]) if o["event_ids"] else []
                event_ids.extend(evs)
                evds = json.loads(o["evidence_ids"]) if o["evidence_ids"] else []
                evidence_ids.extend(evds)
            except Exception:
                pass

        score, breakdown = calculate_insight_score(
            anomaly=min(100.0, (max_dwell / 180.0) * 100.0),
            persistence=min(100.0, (max_dwell / 120.0) * 90.0),
            spatial_significance=70.0,
            cross_camera_correlation=10.0,
            density_activity_change=40.0,
            incident_relevance=40.0,
            camera_reliability=100.0,
        )

        prev_priority = existing["priority"] if existing else None
        priority = get_priority(score, prev_priority)

        # Extract movement, walking, and color telemetry
        evidence_intel = self.evidence_analyzer.analyze_for_insight(
            insight_type="UNUSUAL_DWELL",
            active_obs=active_obs,
            evidence_ids=evidence_ids,
            track_ids=track_ids,
        )

        signals = {
            "duration_seconds": round(max_dwell, 1),
            "dwell_delta": f"Normal ~25s → Current {int(max_dwell)}s",
            "score_breakdown": breakdown,
            "movement_intel": evidence_intel.get("movement_items", []),
            "color_intel": evidence_intel.get("color_items", []),
            "evidence_snapshots": evidence_intel.get("snapshots", []),
            "movement_summary": evidence_intel.get("movement_summary"),
            "color_summary": evidence_intel.get("color_summary"),
            "walking_count": evidence_intel.get("walking_count", 0),
            "primary_color": evidence_intel.get("primary_color_label"),
            "primary_direction": evidence_intel.get("primary_direction"),
        }
        baseline = {"normal_dwell": 25.0, "normal_activity": 30}

        # Check if CRITICAL: prompt Qwen model
        if priority == "CRITICAL":
            qwen_res = self.explainer.summarize_critical_insight(
                insight_type="UNUSUAL_DWELL",
                signals=signals,
                baseline=baseline,
                cameras=[camera_id],
                zones=[zone_name],
                evidence_intel=evidence_intel,
            )
            summary = qwen_res["summary"]
            confidence = qwen_res["confidence"]
            factors = qwen_res["reasoning_factors"]
            signals["qwen_analysis"] = qwen_res
        else:
            explanation = self.explainer.explain_insight(
                insight_type="UNUSUAL_DWELL",
                signals=signals,
                baseline=baseline,
                cameras=[camera_id],
                zones=[zone_name],
                evidence_ids=evidence_ids,
            )
            summary = explanation["summary"]
            confidence = explanation["confidence"]
            factors = [
                f"Movement: {evidence_intel.get('movement_summary')}",
                f"Attire: {evidence_intel.get('color_summary')}",
                *explanation["reasoning_factors"],
            ]

        if existing:
            update_sql = "UPDATE insights SET score=?, priority=?, signals=?, updated_at=?"
            update_params = [score, priority, json.dumps(signals), now_str]
            if priority == "CRITICAL":
                update_sql += ", summary=?, reasoning_factors=?"
                update_params.extend([summary, json.dumps(factors)])
            update_sql += " WHERE insight_id=?"
            update_params.append(existing["insight_id"])
            self.db.execute(update_sql, tuple(update_params))
            self.db.commit()
            return self.get_insight(existing["insight_id"])

        insight_id = f"INS-{uuid.uuid4().hex[:6].upper()}"
        self.db.execute(
            """INSERT INTO insights (
                insight_id, timestamp, type, summary, score, confidence, priority,
                camera_ids, zone_ids, track_ids, event_ids, evidence_ids,
                signals, baseline_comparison, reasoning_factors, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                insight_id,
                now_str,
                "UNUSUAL_DWELL",
                summary,
                score,
                confidence,
                priority,
                json.dumps([camera_id]),
                json.dumps([zone_id]),
                json.dumps(track_ids),
                json.dumps(list(set(event_ids))),
                json.dumps(list(set(evidence_ids))),
                json.dumps(signals),
                json.dumps(baseline),
                json.dumps(factors),
                "ACTIVE",
                now_str,
                now_str,
            ),
        )
        self.db.commit()
        return self.get_insight(insight_id)

    def _process_cross_camera_insight(self, obs_row: Any, rel_cams: list[str]) -> dict[str, Any] | None:
        """Create or update a CROSS_CAMERA_PATTERN insight with walking and color intelligence."""
        track_id = obs_row["track_id"]
        existing = self.db.execute(
            "SELECT * FROM insights WHERE track_ids LIKE ? AND type='CROSS_CAMERA_PATTERN' AND status='ACTIVE'",
            (f"%{track_id}%",),
        ).fetchone()
        if existing:
            return None

        now_str = now_iso()
        score, breakdown = calculate_insight_score(
            anomaly=50.0,
            persistence=60.0,
            spatial_significance=60.0,
            cross_camera_correlation=90.0,
            density_activity_change=30.0,
            incident_relevance=40.0,
            camera_reliability=100.0,
        )
        priority = get_priority(score)

        # Extract movement, walking, and color telemetry
        evidence_intel = self.evidence_analyzer.analyze_for_insight(
            insight_type="CROSS_CAMERA_PATTERN",
            active_obs=[obs_row],
            evidence_ids=[],
            track_ids=[track_id],
        )

        signals = {
            "cameras": rel_cams,
            "cameras_delta": " → ".join(rel_cams),
            "duration_seconds": float(obs_row["dwell_seconds"] or 45.0),
            "score_breakdown": breakdown,
            "movement_intel": evidence_intel.get("movement_items", []),
            "color_intel": evidence_intel.get("color_items", []),
            "evidence_snapshots": evidence_intel.get("snapshots", []),
            "movement_summary": evidence_intel.get("movement_summary"),
            "color_summary": evidence_intel.get("color_summary"),
            "walking_count": evidence_intel.get("walking_count", 0),
            "primary_color": evidence_intel.get("primary_color_label"),
            "primary_direction": evidence_intel.get("primary_direction"),
        }
        baseline = {"normal_cameras": 1}

        # Check if CRITICAL
        if priority == "CRITICAL":
            qwen_res = self.explainer.summarize_critical_insight(
                insight_type="CROSS_CAMERA_PATTERN",
                signals=signals,
                baseline=baseline,
                cameras=rel_cams,
                zones=[obs_row["zone_id"]] if obs_row["zone_id"] else ["facility"],
                evidence_intel=evidence_intel,
            )
            summary = qwen_res["summary"]
            confidence = qwen_res["confidence"]
            factors = qwen_res["reasoning_factors"]
            signals["qwen_analysis"] = qwen_res
        else:
            explanation = self.explainer.explain_insight(
                insight_type="CROSS_CAMERA_PATTERN",
                signals=signals,
                baseline=baseline,
                cameras=rel_cams,
                zones=[obs_row["zone_id"]] if obs_row["zone_id"] else ["facility"],
            )
            summary = explanation["summary"]
            confidence = explanation["confidence"]
            factors = [
                f"Movement: {evidence_intel.get('movement_summary')}",
                f"Attire: {evidence_intel.get('color_summary')}",
                *explanation["reasoning_factors"],
            ]

        insight_id = f"INS-{uuid.uuid4().hex[:6].upper()}"
        self.db.execute(
            """INSERT INTO insights (
                insight_id, timestamp, type, summary, score, confidence, priority,
                camera_ids, zone_ids, track_ids, event_ids, evidence_ids,
                signals, baseline_comparison, reasoning_factors, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                insight_id,
                now_str,
                "CROSS_CAMERA_PATTERN",
                summary,
                score,
                confidence,
                priority,
                json.dumps(rel_cams),
                json.dumps([obs_row["zone_id"]] if obs_row["zone_id"] else []),
                json.dumps([track_id]),
                json.dumps([]),
                json.dumps([]),
                json.dumps(signals),
                json.dumps(baseline),
                json.dumps(factors),
                "ACTIVE",
                now_str,
                now_str,
            ),
        )
        self.db.commit()
        return self.get_insight(insight_id)

    def get_insights(
        self,
        priority: str | None = None,
        status: str | None = None,
        type_: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List persisted insights with filtering."""
        query = "SELECT * FROM insights WHERE 1=1"
        args: list[Any] = []
        if priority:
            query += " AND priority=?"
            args.append(priority.upper())
        if status:
            query += " AND status=?"
            args.append(status.upper())
        if type_:
            query += " AND type=?"
            args.append(type_.upper())

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args.extend([max(1, min(100, limit)), max(0, offset)])

        rows = self.db.execute(query, tuple(args)).fetchall()
        return [self._format_row(r) for r in rows]

    def get_insight(self, insight_id: str) -> dict[str, Any] | None:
        """Retrieve single insight by identifier with full details."""
        row = self.db.execute("SELECT * FROM insights WHERE insight_id=?", (insight_id,)).fetchone()
        if not row:
            return None
        return self._format_row(row)

    def get_summary(self) -> dict[str, Any]:
        """Header counts: Active, Important, New, Resolved."""
        total = self.db.execute("SELECT COUNT(*) FROM insights").fetchone()[0]
        active = self.db.execute("SELECT COUNT(*) FROM insights WHERE status='ACTIVE'").fetchone()[0]
        important = self.db.execute("SELECT COUNT(*) FROM insights WHERE priority IN ('IMPORTANT', 'CRITICAL') AND status='ACTIVE'").fetchone()[0]
        critical = self.db.execute("SELECT COUNT(*) FROM insights WHERE priority='CRITICAL' AND status='ACTIVE'").fetchone()[0]
        resolved = self.db.execute("SELECT COUNT(*) FROM insights WHERE status='RESOLVED'").fetchone()[0]

        # "New" = created in last 1 hour
        cutoff_1h = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        new_cnt = self.db.execute("SELECT COUNT(*) FROM insights WHERE created_at >= ? AND status='ACTIVE'", (cutoff_1h,)).fetchone()[0]

        return {
            "total_insights": total,
            "active": active,
            "important": important,
            "critical": critical,
            "new": new_cnt,
            "resolved": resolved,
        }

    def record_feedback(
        self,
        insight_id: str,
        operator_feedback: str,
        camera_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Record operator feedback (CONFIRM, DISMISS, NOT_SURE)."""
        fb_id = f"FB-{uuid.uuid4().hex[:8].upper()}"
        stamp = now_iso()
        norm_fb = operator_feedback.upper()

        self.db.execute(
            "INSERT INTO insight_feedback (feedback_id, insight_id, camera_id, operator_feedback, notes, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (fb_id, insight_id, camera_id, norm_fb, notes, stamp),
        )

        if norm_fb == "DISMISS" or norm_fb == "RESOLVED":
            self.db.execute("UPDATE insights SET status='RESOLVED', updated_at=? WHERE insight_id=?", (stamp, insight_id))
        elif norm_fb == "CONFIRM":
            self.db.execute("UPDATE insights SET status='ACKNOWLEDGED', updated_at=? WHERE insight_id=?", (stamp, insight_id))

        self.db.commit()
        return {
            "feedback_id": fb_id,
            "insight_id": insight_id,
            "status": "RECORDED",
            "operator_feedback": norm_fb,
            "timestamp": stamp,
        }

    def _format_row(self, row: sqlite3.Row | Any) -> dict[str, Any]:
        if not row:
            return {}
        d = dict(row)
        for field in ("camera_ids", "zone_ids", "track_ids", "event_ids", "evidence_ids", "reasoning_factors"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    d[field] = []
            else:
                d[field] = []
        for field in ("signals", "baseline_comparison"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    d[field] = {}
            else:
                d[field] = {}
        return d
