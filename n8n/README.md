# n8n: RoomService Life workflow

Calendar and email for the `life` agent (SPEC §14). The workflow has no send-email tool: it can read mail and create drafts only.

## 1. Start n8n

```bash
echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 16)" > infra/.env   # 32 chars; infra/.env is git-ignored
docker compose -f infra/docker-compose.n8n.yml --env-file infra/.env up -d
```

Open `http://localhost:5678` (always `localhost`, so the OAuth redirect matches) and create the owner account. Timezone is `Asia/Kolkata` (compose sets `GENERIC_TIMEZONE` and `TZ`; the workflow settings also say `Asia/Kolkata`).

## 2. Credentials (never exported; create them in the n8n UI)

1. **Header Auth** for the webhook: name `X-RoomService-Token`, value = `N8N_LIFE_TOKEN` from `.env` (32 random chars).
2. **Chat model**: if you have an `ANTHROPIC_API_KEY`, create an *Anthropic API* credential and keep the *Anthropic Chat Model* node. Otherwise create an *OpenAI API* credential and swap that node for an *OpenAI Chat Model* (connect it to the AI Agent's chat-model input).
3. **Google** (Google Cloud Console):
   - New project, enable the **Google Calendar API** and **Gmail API**.
   - OAuth consent screen: External, add the owner's Gmail as a **test user**.
   - Credentials, OAuth client ID, type **Web application**, authorised redirect URI exactly `http://localhost:5678/rest/oauth2-credential/callback`.
   - In n8n create **Google Calendar OAuth2 API** and **Gmail OAuth2 API** credentials with that client ID/secret and click *Sign in with Google*.

## 3. Import and activate

1. n8n: Workflows, Import from File, `n8n/life.workflow.json`.
2. Open each node that shows a red credential warning and pick the credential from step 2 (Webhook: Header Auth; AI Agent chat model; the two Calendar and two Gmail tools).
3. Click **Activate** (top right). The production URL is `http://localhost:5678/webhook/roomservice-life`. The test URL (`/webhook-test/...`) is not what RoomService calls.

## 4. Check it

```bash
curl -s -X POST http://localhost:5678/webhook/roomservice-life \
  -H "X-RoomService-Token: $N8N_LIFE_TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"ping","sender_name":"me","room_name":"roomservice-hq","mission_slug":null,"now_iso":"2026-11-07T09:00:00+05:30","tz":"Asia/Kolkata","mode":"ask"}'
uv run roomservice doctor        # "n8n reachable, token accepted"
uv run roomservice up --fire morning-brief
```

## Fallback: Code-tool (if Google OAuth is not ready)

Delete the two Calendar and two Gmail tool nodes and add one **Code Tool** connected to the AI Agent's tool input, description "calendar and email", returning:

```js
return "calendar not connected yet; I would: " + query;
```

Life then answers honestly that calendar is not connected. Re-add the Google tools once OAuth works.
