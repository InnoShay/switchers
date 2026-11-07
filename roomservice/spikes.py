"""Spikes S0-S8 (SPEC §20.1): `roomservice spike <id>`. Results go in DECISIONS.md by hand."""

from __future__ import annotations

import asyncio
import io
import json
import time
from collections.abc import Awaitable, Callable

from rich.console import Console

from roomservice import store
from roomservice.bus import Bus
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import Settings, load_settings
from roomservice.contracts.switch import DomainEvent, OpError
from roomservice.switch.connection import RoomConnection
from roomservice.switch.http import SwitchHTTPClient
from roomservice.switch.rooms import RoomWatcher, detect_kind, parse_rooms

console = Console()
SPIKE_AGENT = "rs-spike"
SPIKE_IDS = [f"s{i}" for i in range(9)]


class SpikeFailed(Exception):
    """Raised by a spike to report FAIL with a fix hint."""


def _ok(msg: str) -> None:
    console.print(f"[green]PASS[/green] {msg}")


def _info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")


def _steps(title: str, steps: list[str]) -> None:
    console.print(f"[bold]{title}[/bold]")
    for i, s in enumerate(steps, 1):
        console.print(f"  {i}. {s}")


def _creds(settings: Settings, *names: str) -> tuple[str, str, str]:
    """(name, agent_id, api_key) for the first agent that is registered locally."""
    url = str(settings.switch_url).rstrip("/")
    for name in names:
        c = store.load_agent_creds(url, name)
        if c:
            return name, c["id"], c["api_key"]
    raise SpikeFailed(f"no registered agent among {list(names)}; run `uv run roomservice register`")


def _client(settings: Settings, *names: str) -> tuple[SwitchHTTPClient, str, str]:
    name, agent_id, key = _creds(settings, *names)
    url = str(settings.switch_url).rstrip("/")
    return SwitchHTTPClient(url, agent_id=agent_id, api_key=key), agent_id, key


async def _list_rooms(http: SwitchHTTPClient, settings: Settings) -> list[RoomInfo]:
    out = []
    for raw in parse_rooms(await http.op("list_rooms", {})):
        rid = str(raw.get("id") or raw.get("room_id"))
        name = str(raw.get("name") or rid)
        out.append(
            RoomInfo(id=rid, name=name, kind=detect_kind(rid, name, settings.roomservice_hq_rooms))
        )
    return out


def _pick_room(rooms: list[RoomInfo]) -> RoomInfo:
    if not rooms:
        raise SpikeFailed(
            "the agent sees no rooms; in Mattermost HQ run `!invite-agent @rs-spike` "
            "(or @desk-laptop for the configured agent)"
        )
    return next((r for r in rooms if r.kind == RoomKind.HQ), rooms[0])


async def _tail_logs(seconds: float, needles: list[str]) -> None:
    """Print runtime.jsonl lines containing any needle, for `seconds`."""
    path = store.logs_dir() / "runtime.jsonl"
    pos = path.stat().st_size if path.exists() else 0
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        await asyncio.sleep(1)
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            f.seek(pos)
            chunk = f.read()
            pos = f.tell()
        for line in chunk.splitlines():
            if any(n.lower() in line.lower() for n in needles):
                console.print(line)


# -- S0 / S1 ------------------------------------------------------------------------------


async def s0(settings: Settings) -> None:
    """Second machine reaches the server? Run on the OTHER machine with SWITCH_URL set."""
    _info(f"GET {str(settings.switch_url).rstrip('/')}/health from this machine")
    http = SwitchHTTPClient(str(settings.switch_url))
    try:
        if not await http.health():
            raise SpikeFailed("no 200 from /health; use the SSH port forward from SPEC §5.2")
    finally:
        await http.aclose()
    _ok("server reachable from this machine")


async def s1(settings: Settings) -> None:
    """Base URL right?"""
    http = SwitchHTTPClient(str(settings.switch_url))
    try:
        if not await http.health():
            raise SpikeFailed("GET /health did not return 200; fix SWITCH_URL in .env")
    finally:
        await http.aclose()
    _ok(f"{settings.switch_url} /health -> 200")


# -- S2 -----------------------------------------------------------------------------------


async def s2(settings: Settings, seconds: float = 30) -> None:
    """Register rs-spike, open a WebSocket on HQ, answer pings for 30 s."""
    if settings.switch_registration_key is None:
        raise SpikeFailed("SWITCH_REGISTRATION_KEY is not set in .env")
    url = str(settings.switch_url).rstrip("/")
    reg = SwitchHTTPClient(
        url, registration_key=settings.switch_registration_key.get_secret_value()
    )
    try:
        agent_id, key = await reg.register(
            SPIKE_AGENT,
            "RS spike",
            "RoomService spike agent (safe to delete).",
            "roomservice-spike",
            overwrite=True,
        )
    finally:
        await reg.aclose()
    store.save_agent_creds(url, SPIKE_AGENT, agent_id, key)
    _ok("registered rs-spike (key stored, not printed)")

    http = SwitchHTTPClient(url, agent_id=agent_id, api_key=key)
    try:
        await http.op(
            "update_agent_detail", {"agent_id": agent_id, "addressing": "owner_and_owner_agents"}
        )
        rooms = await _list_rooms(http, settings)
        if not rooms:
            raise SpikeFailed(
                "rs-spike sees no rooms; in HQ send `!invite-agent @rs-spike`, then re-run"
            )
        room = _pick_room(rooms)
        _info(f"opening WebSocket on '{room.name}' for {seconds:.0f}s")

        async def on_event(r: RoomInfo, ev: DomainEvent) -> None:
            _info(f"event {ev.type} seq={ev.sequence}")

        conn = RoomConnection(
            base_url=url, agent_id=agent_id, api_key=key, http=http, room=room,
            on_event=on_event, bus=Bus(),
        )  # fmt: skip
        conn.start()
        await asyncio.sleep(seconds)
        await conn.stop()
        if conn.fatal:
            raise SpikeFailed(f"connection stopped: {conn.stop_reason}")
        if not conn.state_received:
            raise SpikeFailed(
                "no connection_state frame; check key type / scheme / additional_headers"
            )
        if conn.evictions:
            raise SpikeFailed(f"evicted: {conn.evictions}")
        _ok(f"connection_state (generation {conn.generation}), no eviction in {seconds:.0f}s")
    except OpError as e:
        raise SpikeFailed(f"Switch refused: {e}") from e
    finally:
        await http.aclose()


# -- S3 -----------------------------------------------------------------------------------


def _png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (320, 120), (16, 20, 28))
    ImageDraw.Draw(img).text((16, 50), "RoomService S3 spike", fill=(124, 156, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


async def s3(settings: Settings) -> None:
    """post() text + upload() PNG to HQ (else any room)."""
    http, _, _ = _client(settings, SPIKE_AGENT, settings.roomservice_agent)
    try:
        room = _pick_room(await _list_rooms(http, settings))
        event_id = await http.post(room.id, "RoomService S3 spike: text post")
        _ok(f"post() -> event {event_id} in '{room.name}'")
        res = await http.upload(
            room.id, [("s3.png", _png(), "image/png")], "RoomService S3 spike: PNG"
        )
        _ok(f"upload() -> {json.dumps(res)[:120]}")
        console.print(f"Now confirm both are visible in '{room.name}' in Mattermost.")
    except OpError as e:
        raise SpikeFailed(f"Switch refused: {e}") from e
    finally:
        await http.aclose()


# -- S4 / S5 / S7 : guided manual steps + watching ------------------------------------------


async def s4(settings: Settings, seconds: float = 180) -> None:
    """Agent-run mission template: owner says 'test mission spike room' in HQ."""
    _steps("S4 mission template", [
        "Start the desk (`uv run roomservice up`) if RS-07 is merged; otherwise skip.",
        "In Mattermost roomservice-hq say: test mission spike room",
        f"Waiting up to {seconds:.0f}s for a room named mission-spike-room ...",
    ])  # fmt: skip
    http, _, _ = _client(settings, settings.roomservice_agent, SPIKE_AGENT)
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rooms = await _list_rooms(http, settings)
            hit = next((r for r in rooms if r.name == "mission-spike-room"), None)
            if hit:
                _ok(f"room '{hit.name}' exists (id {hit.id}). Check crew, brief doc and kickoff.")
                return
            await asyncio.sleep(2)
        raise SpikeFailed("no mission-spike-room; use the concierge fallback path (SPEC §10.4)")
    finally:
        await http.aclose()


async def s5(settings: Settings, seconds: float = 300) -> None:
    """Agent 'yes' answers a builder permission request."""
    _steps("S5 builder permission", [
        "Start the desk with relay on (`uv run roomservice up`).",
        "In a mission room ask: @builder run npm i left-pad",
        "Builder should post a permission request; the desk should post `yes`.",
        "Pass if the builder proceeds. Fail: set ROOMSERVICE_RELAY_APPROVALS=false.",
        f"Watching runtime logs for {seconds:.0f}s ...",
    ])  # fmt: skip
    await _tail_logs(seconds, ["permission", "approval", "yes"])


async def _watch_messages(settings: Settings, seconds: float) -> None:
    http, _, _ = _client(settings, settings.roomservice_agent, SPIKE_AGENT)
    name, agent_id, key = _creds(settings, settings.roomservice_agent, SPIKE_AGENT)

    async def on_event(room: RoomInfo, ev: DomainEvent) -> None:
        if ev.type == "message":
            p = ev.payload
            console.print(
                f"[{room.kind.value}] {room.name}: addressed={p.get('addressed')} "
                f"{p.get('sender_name')}: {str(p.get('body'))[:80]}"
            )

    watcher = RoomWatcher(
        http, base_url=str(settings.switch_url), agent_id=agent_id, api_key=key,
        hq_rooms=settings.roomservice_hq_rooms, on_event=on_event, bus=Bus(),
    )  # fmt: skip
    await watcher.start()
    try:
        await asyncio.sleep(seconds)
    finally:
        await watcher.stop()
        await http.aclose()


async def s6(settings: Settings, seconds: float = 60) -> None:
    """New room visible in <= 5 s."""
    http, _, _ = _client(settings, settings.roomservice_agent, SPIKE_AGENT)
    try:
        before = {r.id for r in await _list_rooms(http, settings)}
        await asyncio.to_thread(input, "Press Enter, then create a new room right away... ")
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            new = [r for r in await _list_rooms(http, settings) if r.id not in before]
            if new:
                dt = time.monotonic() - t0
                _ok(f"room '{new[0].name}' visible after {dt:.1f}s ({'<=' if dt <= 5 else '>'} 5s)")
                if dt > 5:
                    console.print("[yellow]Over 5s: poll every 2s instead of 3s.[/yellow]")
                return
            await asyncio.sleep(0.5)
        raise SpikeFailed("no new room seen")
    finally:
        await http.aclose()


async def s7(settings: Settings, seconds: float = 180) -> None:
    """@hands reaches the holder (mission) and the alias works (HQ)."""
    _steps("S7 @hands addressing", [
        "Make sure the desk holds the `hands` role (assume_role) and the alias is set in HQ.",
        "Post `@hands status` in an HQ room and in a mission room.",
        "Pass if both lines below show addressed=True (fallback: holder per list_roles).",
        f"Watching all rooms for {seconds:.0f}s ...",
    ])  # fmt: skip
    await _watch_messages(settings, seconds)


LEASE_PASS_S = 15.0  # SPEC §20.1 S8: backup must hold the role within 15 s


class LapseMeter:
    """Pure timing logic of S8: when did `hands` stop being held by the original holder?"""

    def __init__(self) -> None:
        self.holder: str | None = None  # who held hands before the kill
        self.killed_at: float | None = None
        self.lapsed_at: float | None = None
        self.new_holder: str | None = None

    def observe(self, t: float, holder: str | None) -> None:
        if self.killed_at is None:
            if holder:
                self.holder = holder
            return
        if self.lapsed_at is None and holder != self.holder:
            self.lapsed_at = t
            self.new_holder = holder

    def kill(self, t: float) -> None:
        self.killed_at = t

    @property
    def lapse_s(self) -> float | None:
        if self.killed_at is None or self.lapsed_at is None:
            return None
        return max(0.0, self.lapsed_at - self.killed_at)


def recommend_mode(lapse_s: float | None) -> str:
    """lease if the role moved within 15 s of the kill, else explicit (also if it never moved)."""
    return "lease" if lapse_s is not None and lapse_s <= LEASE_PASS_S else "explicit"


async def s8(settings: Settings, seconds: float = 120) -> None:
    """Lease lapse time: backup holds the role within 15 s of the laptop dying."""
    from roomservice.agents.desk import hands_holder

    _steps("S8 lease lapse", [
        "Laptop runtime holds `hands` (a mission); `roomservice backup` runs on machine 2.",
        "Run this spike as rs-spike (it will not steal a connection from either desk).",
        "When prompted, kill the laptop runtime (Ctrl-C / close the lid), then press Enter.",
        f"The spike then polls list_roles for up to {seconds:.0f}s and times the lapse.",
    ])  # fmt: skip
    http, _, _ = _client(settings, SPIKE_AGENT, settings.roomservice_agent)
    name, agent_id, key = _creds(settings, SPIKE_AGENT, settings.roomservice_agent)
    try:
        room = _pick_room(await _list_rooms(http, settings))
        conn = RoomConnection(
            base_url=str(settings.switch_url), agent_id=agent_id, api_key=key, http=http,
            room=room, on_event=_noop, bus=Bus(),
        )  # fmt: skip
        conn.start()
        meter = LapseMeter()
        loop = asyncio.get_running_loop()
        prompt: asyncio.Future | None = None
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds + 60:
            await asyncio.sleep(1)
            if not conn.connected:
                continue
            try:
                holder = hands_holder(await http.op("list_roles", {}, conn.connection_id))
            except OpError as e:
                _info(f"list_roles: {e}")
                continue
            now = time.monotonic()
            meter.observe(now, holder)
            if meter.killed_at is None and meter.holder and prompt is None:
                console.print(f"hands is held by [bold]{meter.holder}[/bold].")
                console.print("Kill the laptop runtime NOW, then press Enter ...")
                prompt = loop.run_in_executor(None, input)
            if prompt is not None and prompt.done() and meter.killed_at is None:
                meter.kill(now)
                t0 = now  # the watch window starts at the kill
            if meter.lapse_s is not None:
                break
            if meter.killed_at is not None and now - meter.killed_at > seconds:
                break
        await conn.stop()
        lapse = meter.lapse_s
        if lapse is None:
            console.print("[red]FAIL[/red] hands never left its holder in the window.")
        else:
            verdict = "[green]PASS[/green]" if lapse <= LEASE_PASS_S else "[yellow]SLOW[/yellow]"
            console.print(
                f"{verdict} hands moved to {meter.new_holder or 'nobody'} after {lapse:.1f}s"
            )
        console.print(f"Recommended ROOMSERVICE_HANDOFF_MODE={recommend_mode(lapse)}")
        console.print("Record it in DECISIONS.md: `RS-12: S8 lapse <n>s — mode <mode>`")
    finally:
        await http.aclose()


async def _noop(room: RoomInfo, ev: DomainEvent) -> None:
    return None


SPIKES: dict[str, Callable[[Settings], Awaitable[None]]] = {
    "s0": s0, "s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5, "s6": s6, "s7": s7, "s8": s8,
}  # fmt: skip


def run_spike(spike_id: str) -> bool:
    """Run one spike; returns True on pass. Prints PASS/FAIL lines."""
    spike_id = spike_id.lower()
    if spike_id not in SPIKES:
        console.print(
            f"[red]unknown spike '{spike_id}'; choose one of {', '.join(SPIKE_IDS)}[/red]"
        )
        return False
    try:
        asyncio.run(SPIKES[spike_id](load_settings()))
    except SpikeFailed as e:
        console.print(f"[red]FAIL[/red] {e}")
        return False
    except OpError as e:
        console.print(f"[red]FAIL[/red] Switch refused: {e}")
        return False
    except KeyboardInterrupt:
        console.print("stopped")
    except Exception as e:  # one line with the fix, no stack trace
        console.print(f"[red]FAIL[/red] {type(e).__name__}: {e}. Is SWITCH_URL reachable?")
        return False
    return True


__all__ = ["SPIKES", "SpikeFailed", "run_spike"]
