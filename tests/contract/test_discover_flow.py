"""RS-07: `boot <newdir>` where the directory is created while the desk is running."""

import json

from roomservice import store
from roomservice.agents.desk import DeskAgent, add_owner
from roomservice.bus import Bus
from roomservice.contracts.config import Settings, load_desk_config
from roomservice.desk.os.dry import DryAdapter
from tests.contract.fake_switch import FakeSwitch, message_frame, sleep
from tests.contract.test_desk_flow import bodies, wait_for


async def test_boot_directory_created_during_test(
    fixtures_dir, monkeypatch, tmp_path, projects_root
):
    monkeypatch.chdir(tmp_path)
    app = projects_root / "brandnew"
    scripts = [[sleep(0.4), message_frame(1, "@hands boot brandnew"), sleep(0.8),
                message_frame(2, "@hands boot nope-nothing")]]  # fmt: skip
    fake = await FakeSwitch(scripts).start()
    monkeypatch.setenv("SWITCH_URL", fake.url)
    store.save_agent_creds(fake.url, "desk-laptop", "id-desk-laptop", "key-desk-laptop")
    add_owner("@owner:srv", "owner", "roomservice-hq")
    adapter = DryAdapter(delay_s=0.01)
    agent = DeskAgent(
        cfg=load_desk_config(fixtures_dir / "desk_example.yaml"),
        settings=Settings(),
        adapter=adapter,
        bus=Bus(),
    )
    try:
        await agent.start()
        app.mkdir()  # created after the desk is already up, no config entry
        (app / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}}))
        await wait_for(lambda: any("no project called nope-nothing" in b for b in bodies(fake)))
        got = bodies(fake)
        assert any(b.startswith("✅ boot brandnew · editor, 1 terminal") for b in got)
        assert ("open_terminal", (str(app), "npm run dev", "dev")) in adapter.calls
    finally:
        await agent.stop()
        await fake.stop()
