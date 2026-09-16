"""Bounded CPU transport to a spawned DreamDB writer; never forks CUDA.

The fixed arena bounds encoded in-flight batches, not process RSS. Producer event
objects + one serialization, child decoding, model startup and SDK allocations
are separate. Pickle is only private same-program IPC, never a storage format or
an input accepted from a dataset/client.
"""

from __future__ import annotations

import multiprocessing as mp
import pickle
import time
from contextlib import suppress
from pathlib import Path

from store import LocalRunWriter


def _write(root, metadata, model, arena, slot_bytes, conn):
    try:
        writer = LocalRunWriter(Path(root), metadata, model)
        conn.send(("ready", writer.dataset.current_manifest()))
        while True:
            command = conn.recv()
            if command[0] == "finish":
                conn.send(("finished", writer.finish()))
                return
            _, slot, size = command
            start = slot * slot_bytes
            payload = bytes(memoryview(arena).cast("B")[start : start + size])
            events = pickle.loads(payload)
            tip = writer.append(events)
            del events, payload
            conn.send(("ack", slot, tip))
    except BaseException as exc:
        # Propagate the original failure; never mark an interrupted run complete.
        with suppress(BrokenPipeError, EOFError, OSError):
            conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


class BoundedWriter:
    def __init__(
        self, root, metadata, model, *, slots=2, slot_bytes=131072, max_rows=64, timeout=120
    ):
        if slots <= 0 or slot_bytes <= 0 or max_rows <= 0 or timeout <= 0:
            raise ValueError("positive writer limits required")
        ctx = mp.get_context("spawn")
        self._arena = ctx.RawArray("B", slots * slot_bytes)
        self._conn, child = ctx.Pipe()
        self._process = ctx.Process(
            target=_write, args=(str(root), metadata, model, self._arena, slot_bytes, child)
        )
        self._free = list(range(slots))
        self._pending = {}
        self._slot_bytes = slot_bytes
        self._max_rows = max_rows
        self._timeout = timeout
        self._closed = False
        self.tip = None
        self.stats = {
            "arena_bytes": slots * slot_bytes,
            "encoded_high_water": 0,
            "backpressure_count": 0,
            "backpressure_seconds": 0.0,
            "submitted_rows": 0,
        }
        self._process.start()
        child.close()
        try:
            kind, value = self._receive()
            if kind != "ready":
                raise RuntimeError(f"unexpected writer startup: {kind}")
            self.tip = value
        except BaseException:
            self.abort()
            raise

    @property
    def pid(self):
        return self._process.pid

    def _receive(self):
        deadline = time.monotonic() + self._timeout
        while not self._conn.poll(0.05):
            if not self._process.is_alive():
                raise RuntimeError(f"writer exited unexpectedly: {self._process.exitcode}")
            if time.monotonic() >= deadline:
                raise TimeoutError("writer acknowledgment timed out; commit state may be ambiguous")
        try:
            message = self._conn.recv()
        except EOFError as exc:
            raise RuntimeError("writer connection closed unexpectedly") from exc
        if message[0] == "error":
            raise RuntimeError(f"writer failed: {message[1]}")
        return message

    def _ack(self):
        kind, slot, tip = self._receive()
        if kind != "ack" or slot not in self._pending:
            raise RuntimeError("unexpected writer acknowledgment")
        del self._pending[slot]
        self._free.append(slot)
        self.tip = tip

    def submit(self, events):
        if self._closed:
            raise RuntimeError("writer is closed")
        try:
            if not 0 < len(events) <= self._max_rows:
                raise ValueError("batch exceeds configured row limit or is empty")
            payload = pickle.dumps(events, protocol=5)
            if len(payload) > self._slot_bytes:
                raise ValueError("batch exceeds slot byte limit; reduce batch size")
            while self._pending and self._conn.poll():
                self._ack()
            if not self._free:
                start = time.monotonic()
                self.stats["backpressure_count"] += 1
                self._ack()
                self.stats["backpressure_seconds"] += time.monotonic() - start
            slot = self._free.pop()
            start = slot * self._slot_bytes
            memoryview(self._arena).cast("B")[start : start + len(payload)] = payload
            self._pending[slot] = len(payload)
            self.stats["encoded_high_water"] = max(
                self.stats["encoded_high_water"], sum(self._pending.values())
            )
            self._conn.send(("batch", slot, len(payload)))
            self.stats["submitted_rows"] += len(events)
        except BaseException:
            self.abort()
            raise

    def drain(self):
        try:
            while self._pending:
                self._ack()
        except BaseException:
            self.abort()
            raise

    def finish(self):
        if self._closed:
            raise RuntimeError("writer is closed")
        try:
            self.drain()
            self._conn.send(("finish",))
            kind, tip = self._receive()
            if kind != "finished":
                raise RuntimeError("missing writer completion")
            self._process.join(timeout=10)
            if self._process.exitcode != 0:
                raise RuntimeError("writer did not exit cleanly")
            self.tip = tip
            self._closed = True
            self._conn.close()
            return tip
        except BaseException:
            self.abort()
            raise

    def abort(self):
        """No run_end. Only this task's writer is stopped; existing data stays."""
        if self._closed:
            return
        self._closed = True
        if self._process.is_alive():
            self._process.terminate()
        self._process.join(timeout=10)
        if self._process.is_alive():
            self._process.kill()
            self._process.join()
        self._conn.close()
