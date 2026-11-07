# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Plain static HTML, CSS and ES modules served by FastAPI (no build step), per SPEC §6. Canvas 2D and Web Audio allowed. Decided by the spec, not by this redesign.

## Users

The owner of a RoomService room (a developer, Yash or Lakshay) watching their own desk work. Primary scene: the demo video for the Flip the Switch hackathon, recorded split-screen (phone Telegram on one side, this HUD fullscreen on the laptop on the other). Secondary scene: the owner glancing at it during a real work session. Judges watch it for 15 seconds first. (Inferred from SPEC §1 and §3.3; user delegated direction.)

## Product Purpose

RoomService turns a physical room into a Switch room. The HUD (Mission Control) is the live view of that room: the crew of agents (you, concierge, builder, scout, hands, life), the desk's actions, approvals waiting on the owner, screenshots, and the hands role moving between machines. Success: someone who has never seen RoomService understands within seconds that agents are acting on a real computer, who is doing what right now, and that the owner holds the leash.

## Positioning

The room has a body: `hands` is a program on the real machine, joined through Switch. The HUD shows that body acting (boot, shot, commit approval, transfer to a second machine). Nobody else in the field shows agents physically acting, nor a role that migrates between machines.

## Constraints

- Fixed event contract (SPEC §8.2): hello, ignition, mission, message, agent_state, action_start, action_end, approval_open, approval_closed, screenshot, speak, transfer, freeze, system. Crew keys and colours are fixed: you #F5F7FA, concierge #7C9CFF, builder #FFB547, scout #4FD1C5, hands #FF5C7A, life #9BE564.
- Keys: F fullscreen, M mute, S freeze, C captions. Reconnect pill. Must work at 1920×1080 and 1280×720, 60 fps orb, no build step, no external runtime assets except Google Fonts.
- All chat text is untrusted: textContent only.
- Chat bodies and screenshots are real user content; the demo script is synthetic and must stay labelled demo.

## Brand commitments

None confirmed. Product name RoomService; tagline "Room service. What are we building today?" (SPEC §0).
