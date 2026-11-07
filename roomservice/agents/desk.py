"""DeskAgent (SPEC §12): the hands. Parse -> allowlist -> approvals -> execute -> receipts."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import re
import secrets
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any

from roomservice import store
from roomservice.agents.base import CREW_KEYS, BaseProtocolAgent, owner_ids, resolve_agent_key
from roomservice.bus import bus as default_bus
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import DeskConfig, Settings, load_settings
from roomservice.contracts.events import (
    ActionEndEvent,
    ActionStartEvent,
    FreezeEvent,
    SystemEvent,
)
from roomservice.contracts.os import OSAdapter
from roomservice.contracts.switch import DomainEvent, MessagePayload, OpError
from roomservice.desk import receipts
from roomservice.desk.actions import (
    ActionContext,
    ActionResult,
    DeskActions,
    Refuse,
    RoleOps,
    Runtime,
)
from roomservice.desk.approvals import Approval, Approvals, parse_resolution
from roomservice.desk.grammar import Command, ParseError, parse_message
from roomservice.desk.ignition import Ignition
from roomservice.desk.state import StateManager
from roomservice.log import get_logger
from roomservice.relay import BuilderAsk, Relay, is_machine_message  # RS-10
from roomservice.voice import SpeechQueue

log = get_logger("desk")

OWNER_ONLY = frozenset({"ok", "no", "freeze", "unfreeze", "exec"})
FROZEN_OK = frozenset({"unfreeze", "status", "help"})
PAIR_TTL_S = 600
PAIR_MAX_FAILS = 5
SWEEP_EVERY_S = 5.0
PARTICIPANT_TTL_S = 30.0
LEASE_RENEW_S = 3.0  # SPEC §15: renew_lease every 3 s while holding `hands`
LEASE_MAX_FAILS = 3  # consecutive failures = role lost
HOLDER_KEYS = ("holder", "held_by", "holder_name", "agent_name", "agent", "assigned_to")


# -- pairing files (SPEC §9.5) ----------------------------------------------------------


def pairing_path():
    return store.home() / "pairing.json"


def new_pairing_code(now: float | None = None) -> str:
    """6 digits, valid 10 minutes. Stored (mode 600) for the running desk to check."""
    code = f"{secrets.randbelow(10**6):06d}"
    store.write_json(
        pairing_path(), {"code": code, "expires_at": (now or time.time()) + PAIR_TTL_S}, secret=True
    )
    return code


def load_owners() -> list[dict[str, str]]:
    data = store.read_json(store.owners_path(), [])
    if isinstance(data, dict):
        data = data.get("owners", [])
    return [d for d in data if isinstance(d, dict) and d.get("sender")]


def add_owner(sender: str, sender_name: str, room_name: str) -> None:
    owners = [
        o for o in load_owners() if not (o["sender"] == sender and o.get("room_name") == room_name)
    ]
    owners.append({"sender": sender, "sender_name": sender_name, "room_name": room_name})
    store.write_json(store.owners_path(), owners, secret=True)


def hands_holder(res: Any) -> str | None:
    """Who holds `hands` according to a tolerant parse of a list_roles result (None = unheld)."""
    roles = res.get("roles", res) if isinstance(res, dict) else res
    if isinstance(roles, dict):  # {"hands": {...}} or {"hands": "holder"}
        roles = [{"name": k, **v} if isinstance(v, dict) else {"name": k, "holder": v}
                 for k, v in roles.items()]  # fmt: skip
    for r in roles if isinstance(roles, list) else []:
        if isinstance(r, dict) and r.get("name") == "hands":
            for k in HOLDER_KEYS:
                if r.get(k):
                    v = r[k]
                    return str(v.get("name") or v.get("id")) if isinstance(v, dict) else str(v)
    return None


# -- jobs -------------------------------------------------------------------------------


@dataclass
class Job:
    cmd: Command
    room: RoomInfo
    thread_id: str | None = None
    sender_name: str = ""
    approved_by: str | None = None
    also_room: RoomInfo | None = None  # where the owner answered an approval (mirrored result)


class _Roles(RoleOps):
    def __init__(self, agent: DeskAgent) -> None:
        self.agent = agent

    async def assume_hands(self, room: RoomInfo) -> tuple[bool, str | None]:
        return await self.agent.assume_hands(room)

    async def release_hands(self) -> bool:
        return await self.agent.release_hands()


class DeskAgent(BaseProtocolAgent):
    def __init__(
        self,
        *,
        cfg: DeskConfig,
        settings: Settings | None = None,
        adapter: OSAdapter | None = None,
        dry_run: bool = False,
        bus: Any = default_bus,
        state: StateManager | None = None,
        **kw: Any,
    ) -> None:
        settings = settings or load_settings()
        name = kw.pop("name", None) or settings.roomservice_agent
        super().__init__(name, settings=settings, bus=bus, **kw)
        if adapter is None:
            from roomservice.desk.os import get_adapter

            adapter = get_adapter(dry_run or settings.roomservice_dry_run)
        self.cfg = cfg
        self.adapter = adapter
        self.speech = SpeechQueue(adapter, cfg.voice)
        self.state = state or StateManager()
        self.frozen = False
        self.current: Job | None = None
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.role_room: RoomInfo | None = None
        self.lease_every_s = LEASE_RENEW_S
        self.last_error: str | None = None
        self._started = time.monotonic()
        self._recent: deque[float] = deque()
        self._rooms_seen: dict[str, RoomInfo] = {}
        self._participants: dict[str, tuple[float, list[dict]]] = {}
        self._pair_fails = 0
        self._tasks: list[asyncio.Task] = []
        self.actions = DeskActions(
            cfg,
            settings,
            adapter,
            self.speech,
            self.state,
            roles=_Roles(self),
            bus=bus,
            runtime=Runtime(
                queue_len=lambda: self.queue.qsize() + (1 if self.current else 0),
                role_held=lambda: self.role_room is not None,
            ),
        )
        self.approvals = Approvals(
            ttl_s=cfg.limits.approval_ttl_s,
            publish=bus.publish,
            on_open=lambda ap: self.actions.speak("Approval needed."),
            on_close=self._on_approval_close,
        )
        self.ignition = Ignition(
            cfg,
            settings,
            owner_ids=owner_ids,
            post=self._safe_reply,
            speak=self.actions.speak,
            enqueue=lambda cmd, room: self._put(Job(cmd, room, sender_name="ignition")),
            lights_webhook=lambda: self.actions.lights(True),
            on_ignite=self._mark_ignited,
            bus=bus,
        )
        # -- RS-10 relay: mirrors mission rooms into HQ (SPEC §13) --
        self.relay = Relay(
            settings=settings,
            approvals=self.approvals,
            hq_rooms=self.hq_rooms,
            post=lambda room_id, text: self.http.post(room_id, text),
            upload=lambda rid, png, fn, cap: self.http.upload(rid, [(fn, png, "image/png")], cap),
            reply=lambda room, text, thread: self._safe_reply(room, text, thread),
            bus=bus,
        )

    def _mark_ignited(self) -> None:
        self.actions.last_ignite = self.actions.clock()

    # -- lifecycle ----------------------------------------------------------------------

    async def start(self) -> None:
        self.bus.set_machine(self.cfg.machine_name)
        self.bus.on_freeze = self._hud_freeze
        self.speech.start()
        self._tasks = [
            asyncio.create_task(self._worker(), name="desk-worker"),
            asyncio.create_task(self._sweeper(), name="desk-sweeper"),
        ]
        await super().start()
        self.start_lease_renewal()

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._tasks = []
        await self.speech.stop()
        if self.bus.on_freeze == self._hud_freeze:
            self.bus.on_freeze = None
        await super().stop()

    def start_lease_renewal(self) -> None:
        """Renew the lease on the `hands` connection every 3 s while holding the role; three
        consecutive failures = role lost (HUD warn). Stopped by `stop()` (task cancel)."""
        self._tasks.append(asyncio.create_task(self._lease_loop(), name="desk-lease"))

    async def _lease_loop(self) -> None:
        fails = 0
        while True:
            await asyncio.sleep(self.lease_every_s)
            room = self.role_room
            if room is None or not room.conn_id:
                fails = 0
                continue
            conn = self.watcher.connections.get(room.id) if self.watcher else None
            if conn is not None and conn.role_lost:  # `room_released` frame already warned
                self.role_room = None
                fails = 0
                continue
            try:
                ok = await self.http.renew_lease(room.conn_id)
            except Exception as e:
                log.warning("renew_lease failed: %s", e)
                ok = False
            fails = 0 if ok else fails + 1
            if fails >= LEASE_MAX_FAILS and self.role_room is room:
                self.role_room = None
                fails = 0
                log.warning("hands lease lost (%d failed renewals)", LEASE_MAX_FAILS)
                self.bus.publish(
                    SystemEvent(
                        level="warn", text=f"hands role lost (lease not renewed): {room.name}"
                    )
                )

    # -- roles --------------------------------------------------------------------------

    async def assume_hands(self, room: RoomInfo) -> tuple[bool, str | None]:
        """Release the role elsewhere, then assume `hands` here. (False, holder) if taken."""
        if self.role_room and self.role_room.id == room.id:
            return True, None
        if self.role_room and self.role_room.conn_id:
            try:
                await self.http.op("release_role", {}, self.role_room.conn_id)
            except OpError as e:
                log.warning("release_role failed: %s", e)
            self.role_room = None
        if not room.conn_id:
            return False, "nobody (this room is not connected yet)"
        try:
            await self.http.op("assume_role", {"role": "hands"}, room.conn_id)
        except OpError as e:
            if e.status == 409 or "held" in str(e).lower():
                return False, await self._role_holder(room)
            raise
        self.role_room = room
        if self.watcher and (conn := self.watcher.connections.get(room.id)):
            conn.role_lost = False
        return True, None

    async def release_hands(self) -> bool:
        room = self.role_room
        if room is None or not room.conn_id:
            return False
        self.role_room = None
        try:
            await self.http.op("release_role", {}, room.conn_id)
        except OpError as e:
            log.warning("release_role failed: %s", e)
        return True

    async def _role_holder(self, room: RoomInfo) -> str | None:
        try:
            res = await self.http.op("list_roles", {}, room.conn_id)
        except OpError:
            return None
        return hands_holder(res)

    # -- inbound ------------------------------------------------------------------------

    def wants_unaddressed(self, room: RoomInfo, msg: MessagePayload) -> bool:
        if self.ignition.matches(room, msg):
            return True
        if self.relay.wants(room, msg):  # RS-10
            return True
        return msg.sender in owner_ids() and parse_resolution(msg.body) is not None

    async def on_message(self, room: RoomInfo, ev: DomainEvent, msg: MessagePayload) -> None:
        self._rooms_seen[room.id] = room
        owner = msg.sender in owner_ids()
        if is_machine_message(msg, ev.payload):  # RS-10: never answer auto-replies / desk-* peers
            return
        await self.relay.observe(room, msg, is_owner=owner, raw=ev.payload)  # RS-10
        if self.ignition.matches(room, msg):
            await self.ignition.fire(room, msg)
        if owner and (parsed := parse_resolution(msg.body)) is not None:
            await self._resolve(room, msg, f"{parsed[0]} {parsed[1]}")
            return
        pm = parse_message(msg.body, msg.addressed, self.cfg.limits.max_commands_per_message)
        for item in pm.items:
            if isinstance(item, ParseError):
                await self._safe_reply(room, receipts.didnt_understand(item.raw), msg.thread_id)
            else:
                await self._dispatch(item, room, msg, owner)
        if pm.refusal:
            await self._safe_reply(room, pm.refusal, msg.thread_id)

    async def _dispatch(self, cmd: Command, room: RoomInfo, msg: MessagePayload, owner: bool):
        v = cmd.verb
        if (v in OWNER_ONLY and not owner) or (v == "exec" and await self._is_agent(room, msg)):
            await self._safe_reply(room, receipts.refused(cmd.raw, "owner only"), msg.thread_id)
        elif v in ("ok", "no"):
            if len(cmd.args) != 1:
                await self._safe_reply(room, receipts.refused(cmd.raw, "usage: ok <CODE>"))
            else:
                await self._resolve(room, msg, f"{v} {cmd.args[0]}")
        elif v == "freeze":
            await self.set_frozen(True, msg.sender_name)
            await self._safe_reply(room, receipts.frozen(msg.sender_name), msg.thread_id)
        elif v == "unfreeze":
            await self.set_frozen(False, msg.sender_name)
            await self._safe_reply(room, receipts.unfrozen(msg.sender_name), msg.thread_id)
        elif v == "pair":
            await self._pair(cmd, room, msg)
        else:
            await self.submit(Job(cmd, room, msg.thread_id, msg.sender_name))

    # -- queue --------------------------------------------------------------------------

    async def submit(self, job: Job) -> bool:
        """Frozen / rate-limit / busy checks with immediate receipts, then enqueue."""
        cmd, room = job.cmd, job.room
        if self.frozen and cmd.verb not in FROZEN_OK:
            await self._safe_reply(room, receipts.refused_frozen(), job.thread_id)
            return False
        limit = self.cfg.limits.actions_per_minute
        now = time.monotonic()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        if len(self._recent) >= limit:
            await self._safe_reply(room, receipts.refused_rate_limit(limit), job.thread_id)
            return False
        busy = self.current is not None or not self.queue.empty()
        if busy:
            current = self.current.cmd.raw if self.current else cmd.raw
            await self._safe_reply(room, receipts.queued(cmd.raw, current), job.thread_id)
        self._put(job)
        return True

    def _put(self, job: Job) -> None:
        self._recent.append(time.monotonic())
        self.queue.put_nowait(job)

    async def _worker(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                await self._run_job(job)
            except Exception as e:  # the worker must survive anything
                self.last_error = f"{type(e).__name__}: {e}"[:200]
                log.exception("desk job crashed")
            finally:
                self.current = None
                self.queue.task_done()

    async def drain(self) -> None:
        await self.queue.join()

    async def _run_job(self, job: Job) -> None:
        cmd, room = job.cmd, job.room
        if self.frozen and cmd.verb not in FROZEN_OK:
            await self._safe_reply(room, receipts.refused_frozen(), job.thread_id)
            return
        self.current = job
        aid = uuid.uuid4().hex[:8]
        self.bus.publish(
            ActionStartEvent(id=aid, verb=cmd.verb, args=list(cmd.args), room=room.name)
        )
        t0 = time.monotonic()

        async def upload(png: bytes, filename: str, caption: str) -> None:
            await self.upload(room, png, filename, caption, job.thread_id)

        ctx = ActionContext(
            room, job.thread_id, job.sender_name, upload, job.approved_by is not None
        )
        pending: str | None = None
        res: ActionResult
        async with self.typing(room):
            try:
                approval_text, project = (None, None)
                if job.approved_by is None:
                    approval_text, project = self.actions.preflight(cmd)
                if approval_text:
                    ap = self.approvals.create(approval_text, room.id, payload=job)
                    pending = receipts.approval_needed(
                        approval_text, project, ap.code, self.cfg.limits.approval_ttl_s
                    )
                    res = ActionResult(True, "awaiting approval", silent=True)
                else:
                    res = await self.actions.execute(cmd, ctx)
            except Refuse as e:
                res = ActionResult(False, reason=str(e))
        secs = time.monotonic() - t0
        summary = res.summary if res.ok else res.reason
        self.bus.publish(
            ActionEndEvent(id=aid, ok=res.ok, ms=int(secs * 1000), summary=summary[:200])
        )
        if not res.ok:
            self.last_error = f"{cmd.raw}: {res.reason}"[:200]
        text = pending or self._receipt(job, res, secs)
        if text:
            await self._safe_reply(room, text, job.thread_id)
            if job.also_room and job.also_room.id != room.id:
                await self._safe_reply(job.also_room, text)

    @staticmethod
    def _receipt(job: Job, res: ActionResult, secs: float) -> str | None:
        cmd = job.cmd
        if not res.ok:
            return res.text or receipts.refused(cmd.raw, res.reason)
        if res.silent:
            return None
        if res.text is not None:
            text = res.text
        elif job.approved_by:
            text = receipts.approved(job.approved_by, res.summary, secs)
        else:
            text = receipts.ok(cmd.verb, cmd.args, res.summary, secs)
            if res.warn:
                text = text.replace("✅", "⚠️", 1)
        if res.detail:
            text += f"\n```\n{res.detail}\n```"
        return text

    # -- approvals ----------------------------------------------------------------------

    async def _resolve(self, room: RoomInfo, msg: MessagePayload, text: str) -> None:
        if await self._is_agent(room, msg):
            return
        r = self.approvals.resolve(text, msg.sender, msg.sender_name, owner_ids(), is_agent=False)
        if r is None:
            return
        if r.approval and isinstance(r.approval.payload, BuilderAsk):  # RS-10
            ok = r.result == "ok"
            if r.result in ("ok", "no"):
                await self.relay.answer(r.approval, ok)
                await self._safe_reply(
                    room,
                    receipts.approved(msg.sender_name, "builder answered yes", 0.0)
                    if ok
                    else receipts.declined(msg.sender_name, r.approval.cmd),
                    msg.thread_id,
                )
            return
        if r.result == "unknown":
            await self._safe_reply(
                room, receipts.refused(text, f"no open approval {r.code}"), msg.thread_id
            )
        elif r.result == "no" and r.approval:
            out = receipts.declined(msg.sender_name, r.approval.cmd)
            await self._safe_reply(self._room_for(r.approval.room_id) or room, out)
            if r.approval.room_id != room.id:
                await self._safe_reply(room, out, msg.thread_id)
        elif r.result == "ok" and r.approval and isinstance(r.approval.payload, Job):
            orig: Job = r.approval.payload
            origin = self._room_for(r.approval.room_id) or orig.room
            self._put(
                Job(
                    orig.cmd,
                    origin,
                    orig.thread_id,
                    orig.sender_name,
                    approved_by=msg.sender_name,
                    also_room=room,
                )
            )
        # "expired" is announced by _on_approval_close

    def _on_approval_close(self, ap: Approval, result: str) -> None:
        if result != "expired":
            return
        room = self._room_for(ap.room_id)
        if room is None:
            return
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(
                self._safe_reply(room, receipts.expired(ap.code, ap.cmd))
            )

    async def _sweeper(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_EVERY_S)
            self.approvals.sweep()
            await self.relay.tick()  # RS-10

    def _room_for(self, room_id: str) -> RoomInfo | None:
        if self.watcher and (r := self.watcher.room(room_id)):
            return r
        return self._rooms_seen.get(room_id)

    # -- identity -----------------------------------------------------------------------

    async def _is_agent(self, room: RoomInfo, msg: MessagePayload) -> bool:
        """Agents never pair or resolve approvals: list_participants + name heuristics."""
        key = resolve_agent_key(msg.sender_name, msg.sender)
        if key in CREW_KEYS:
            return True
        for p in await self._participants_of(room):
            ids = {str(p.get(k)) for k in ("id", "participant_id", "user_id", "sender") if p.get(k)}
            if msg.sender not in ids:
                continue
            kind = str(p.get("type") or p.get("kind") or p.get("participant_type") or "").lower()
            if p.get("is_agent") is True or "agent" in kind:
                return True
        return False

    async def _participants_of(self, room: RoomInfo) -> list[dict]:
        cached = self._participants.get(room.id)
        if cached and time.monotonic() - cached[0] < PARTICIPANT_TTL_S:
            return cached[1]
        out: list[dict] = []
        try:
            res = await self.http.op("list_participants", {}, room.conn_id)
            items = res.get("participants", []) if isinstance(res, dict) else res
            out = [p for p in items if isinstance(p, dict)] if isinstance(items, list) else []
        except Exception as e:
            log.warning("list_participants failed: %s", e)
        self._participants[room.id] = (time.monotonic(), out)
        return out

    # -- pairing (SPEC §9.5) --------------------------------------------------------------

    async def _pair(self, cmd: Command, room: RoomInfo, msg: MessagePayload) -> None:
        def refuse(reason: str) -> Any:
            return self._safe_reply(room, receipts.refused("pair", reason), msg.thread_id)

        if await self._is_agent(room, msg):
            await refuse("agents cannot pair")
            return
        if room.kind != RoomKind.HQ:
            await refuse("pair from an HQ room")
            return
        pend = store.read_json(pairing_path(), None)
        code = cmd.args[0] if len(cmd.args) == 1 else ""
        good = (
            isinstance(pend, dict)
            and time.time() < float(pend.get("expires_at", 0))
            and re.fullmatch(r"\d{6}", code) is not None
            and hmac.compare_digest(str(pend.get("code", "")), code)
        )
        if not good:
            self._pair_fails += 1
            if self._pair_fails >= PAIR_MAX_FAILS:
                pairing_path().unlink(missing_ok=True)
            await refuse("bad or expired pairing code (run `uv run roomservice pair`)")
            return
        add_owner(msg.sender, msg.sender_name, room.name)
        self._pair_fails = 0
        await self._safe_reply(room, receipts.paired(msg.sender_name, room.name), msg.thread_id)

    # -- freeze -------------------------------------------------------------------------

    async def set_frozen(self, on: bool, by: str) -> None:
        self.frozen = on
        self.actions.runtime.frozen = on
        if on:
            self.actions.kill_exec()  # RS-07: stop a running approved `exec`
        self.bus.publish(FreezeEvent(on=on))
        log.info("frozen=%s by %s", on, by)

    async def _hud_freeze(self, on: bool) -> None:
        await self.set_frozen(on, "HUD")
        for room in self.hq_rooms():
            await self._safe_reply(room, receipts.frozen("HUD") if on else receipts.unfrozen("HUD"))

    # -- replies ------------------------------------------------------------------------

    async def reply(self, room: RoomInfo, text: str, thread_id: str | None = None) -> None:
        await super().reply(room, text, thread_id)
        await self.relay.on_desk_post(room, text)  # RS-10

    async def upload(
        self,
        room: RoomInfo,
        png: bytes,
        filename: str,
        caption: str,
        thread_id: str | None = None,
    ) -> None:
        await super().upload(room, png, filename, caption, thread_id)
        await self.relay.on_desk_upload(room, png, filename, caption)  # RS-10

    async def _safe_reply(self, room: RoomInfo, text: str, thread_id: str | None = None) -> None:
        try:
            await self.reply(room, text, thread_id)
        except Exception as e:
            self.last_error = f"reply failed: {type(e).__name__}"
            log.warning("reply failed in %s: %s", room.name, e)

    # -- status (terminal table, SPEC §19) ------------------------------------------------

    def status_snapshot(self) -> dict[str, Any]:
        rooms = self.rooms()
        return {
            "rooms": len(rooms),
            "hq": [r.name for r in rooms if r.kind == RoomKind.HQ],
            "missions": [r.name for r in rooms if r.kind == RoomKind.MISSION],
            "role": f"hands@{self.role_room.name}" if self.role_room else "-",
            "queue": self.queue.qsize() + (1 if self.current else 0),
            "frozen": self.frozen,
            "last_error": self.last_error or (self.watcher.last_error if self.watcher else None),
        }
