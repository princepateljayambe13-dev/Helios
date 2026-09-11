"""Failure-isolated lifecycle supervision for HELIOS runtime engines."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)

@dataclass
class EngineHealth:
    name: str
    status: str = "STARTING"  # STARTING, READY, DEGRADED, FAILED, STOPPED
    restart_attempts: int = 0
    last_error: str | None = None
    updated_at: float = 0
    had_workers: bool = False  # True once a worker task has actually been observed running


class EngineSupervisor:
    """Restarts an isolated engine with bounded backoff, then declares it failed."""
    def __init__(self, max_attempts: int = 3, backoff_seconds: float = 2) -> None:
        self.max_attempts, self.backoff_seconds = max_attempts, backoff_seconds
        self.engines: dict[str, Any] = {}
        self.health: dict[str, EngineHealth] = {}
        self._watcher: asyncio.Task[None] | None = None
        self._stopping = False

    def register(self, name: str, engine: Any) -> None:
        self.engines[name] = engine
        self.health[name] = EngineHealth(name=name, updated_at=time.time())

    async def start(self) -> None:
        self._stopping = False
        for name in self.engines: await self._start(name)
        self._watcher = asyncio.create_task(self._watch(), name="engine-supervisor")

    async def stop(self) -> None:
        self._stopping = True
        if self._watcher: self._watcher.cancel(); await asyncio.gather(self._watcher, return_exceptions=True)
        for engine in self.engines.values(): await engine.stop()
        for state in self.health.values(): state.status="STOPPED"; state.updated_at=time.time()

    async def _start(self, name: str) -> None:
        state, engine = self.health[name], self.engines[name]
        state.status="STARTING"; state.updated_at=time.time()
        try:
            await engine.start()
            state.status="READY" if getattr(engine, "tasks", []) else "DEGRADED"
            state.last_error=None if state.status=="READY" else "Engine started without active workers"
        except Exception as error:
            state.status="DEGRADED"; state.last_error=str(error)
            LOGGER.exception("Engine %s failed to start",name)
        state.updated_at=time.time()

    async def _watch(self) -> None:
        while not self._stopping:
            await asyncio.sleep(1)
            for name, engine in self.engines.items():
                state=self.health[name]
                if state.status in {"FAILED", "STOPPED"}: continue
                tasks=getattr(engine,"tasks",[])
                running=[task for task in tasks if not task.done()]
                if running:
                    state.had_workers=True
                    if state.status!="READY": state.status="READY"; state.last_error=None; state.updated_at=time.time()
                    continue
                # No running workers right now.
                if not tasks and not state.had_workers:
                    # Engine started with no workers (model disabled/unavailable or no feeds).
                    # Do not thrash it with restart attempts; report DEGRADED once and stop.
                    if state.status!="DEGRADED":
                        state.status="DEGRADED"
                        state.last_error="Engine has no active workers (disabled or unavailable)"
                        state.updated_at=time.time()
                    continue
                # An engine that previously had workers lost them all -> this is a real fault.
                failed=any(task.done() and not task.cancelled() for task in tasks)
                if not failed:
                    # Workers exist but none are "done" (e.g. transient state); wait.
                    continue
                if state.restart_attempts >= self.max_attempts:
                    state.status="FAILED"; state.last_error=state.last_error or "Restart limit reached"; state.updated_at=time.time()
                    LOGGER.error("Engine %s declared FAILED after %s attempts",name,state.restart_attempts); continue
                state.restart_attempts += 1; state.status="DEGRADED"; state.updated_at=time.time()
                await asyncio.sleep(self.backoff_seconds * state.restart_attempts)
                if self._stopping: return
                await engine.stop(); await self._start(name)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name:{**asdict(state),"updated_at":state.updated_at} for name,state in self.health.items()}
