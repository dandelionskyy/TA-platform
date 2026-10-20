# BRIDGE handover (web and staff release)

This package adds the BRIDGE web tutor and teacher tools to the supplied TA Platform. **Minerva/LTI and WeChat integration are omitted at the user's request.** The eight backend teaching stages remain: greeting, diagnosis, probing, hinting, productive struggle, explain-back check, explanation and celebration. These two uses of “8” are different.

## Put the files on the server

1. Replace the deployed project with the contents of this ZIP, keeping your existing database volume and the server-side uploads volume. Make a backup before applying a schema migration. The ZIP contains source and built `frontend/dist` assets. Do not copy an old `.env` into a public folder.
2. On a new installation, copy `.env.example` to `.env` on the server. On an existing installation, preserve its `.env` and add only the missing settings. Fill in strong `DB_PASSWORD`, `JWT_SECRET` and `ROBOT_AUTH_KEYS`; set `CORS_ORIGINS` to the actual HTTPS origin. BRIDGE uses the existing `DEEPSEEK_API_KEY` only when `BRIDGE_PROVIDER=deepseek` is explicitly selected.
3. Run an institution-approved multilingual embedding service exposing an Ollama-compatible `POST /api/embed` endpoint and an institution-approved local generation service exposing `POST /api/generate`. Configure `BRIDGE_EMBEDDINGS_URL` with the **full** endpoint, for example `http://model-server:11434/api/embed`; configure `BRIDGE_EMBEDDINGS_MODEL=bge-m3`, `BRIDGE_LLM_URL` with the service base URL, and `BRIDGE_LLM_MODEL` with an installed bilingual model name. Ensure the backend container can reach these internal URLs. The model server, installed model weights and university approval are not in the ZIP. Keep `BRIDGE_ALLOW_LEXICAL_PROTOTYPE=false` for real use.

The generation provider is switchable through `BRIDGE_PROVIDER`. Use `ollama` (the default) with `BRIDGE_LLM_URL` and `BRIDGE_LLM_MODEL` for local or institution-hosted Ollama. Use `deepseek` with `DEEPSEEK_API_KEY`, `BRIDGE_DEEPSEEK_BASE_URL` and `BRIDGE_DEEPSEEK_MODEL` when generation should use the DeepSeek chat API. DeepSeek is a generation provider only; retrieval still requires the separate multilingual `BRIDGE_EMBEDDINGS_URL` service. Do not enable a module until both material processing and a real tutor reply have been verified.
4. Point `nginx/nginx.conf` to your domain and TLS certificate paths, or use your site's equivalent reverse proxy. Its request limit is 51 MiB to allow a 50 MiB multipart document. Check the proxy configuration with `nginx -t` before reloading. Keep the backend API behind this proxy so its public-route request limits apply. If using existing Postgres data, back it up and apply `backend/alembic/versions/0006_bridge_mvp.py` through `alembic upgrade head`. On a new database the app also creates registered tables on startup; migrations are the controlled route for an existing deployment.
5. From the project root run `docker compose up -d --build`. Confirm `GET /api/health` and open `/bridge`. Teacher accounts log in normally and open `/teacher/bridge`. The existing `DEPLOYMENT.md` covers first teacher creation and the rest of the platform.

## Prepare each module

1. A teacher creates a BRIDGE module linked to a course they own. It starts inactive.
2. Upload PDF, DOCX, TXT or MD teaching material (maximum 50 MiB per file). Check `queued` → `processing` → `ready`, or read its failure reason. PDF references have extracted page numbers; DOCX/TXT/MD references are sequential sections. Text-only extraction is used; an image-only PDF needs OCR before upload. An interrupted upload-processing task is recovered at startup and checked again every minute.
3. Review and tag source chunks. Only teacher-reviewed **DEFINITION, EXAMPLE and HINT** chunks can enter the student's scaffolding retrieval; reviewed PARTIAL_SOLUTION, WORKED_SOLUTION and ANSWER chunks are available only after the backend records a successful explain-back and the assessment lock is off. Staff-only solutions live in a separate restricted store and are never queried by student retrieval. At least one reviewed safe chunk is required to activate the module.
4. Replace the module's English/Chinese glossary using CSV or JSON with the client's 50–100 approved STEM terms. The staff tool supports replacement; the client supplies and approves the terms.
5. Use **Compile pack**, edit and approve concept and question drafts, complete misconception placeholders, review 20–50 regression questions, and run **Test module pack**. Add negative questions for absent material, another module and assessment contexts. A pack with incomplete staff content should remain inactive.
6. Toggle **Assessment window** on for a module whenever graded work is active. The backend lock overrides mastery, source category and client requests. Staff can turn the lock off after the window closes.

## What the guard does

The public page creates a random anonymous token tied on the server to one active module. It stores no student account identifier or chat transcript in BRIDGE tables. The token hash, teaching state and short-lived learning events expire after 30 days; daily non-identifying counts remain. The dashboard suppresses groups below ten interactions. Staff and students share the same guarded web API; the two omitted connectors are not present.

The web chat may display the signed-in student's account display name, or an optional preferred name entered on that page, in its welcome and occasional teaching-stage messages. If no name is available, the greeting stays generic. The displayed name is added only by the browser; it is not included in BRIDGE session or tutor requests, model prompts, learning events, citations or staff dashboards. An optional preferred name lasts only while that page is open. Signing in, registering or signing out clears cached BRIDGE sessions on that browser, so anonymous progress from a previous account is not carried to the next account. Account display names are still handled by the existing account service; avoid entering personal details into tutor questions if they should not reach the model.

The included nginx configurations return HTTP 429 when POST requests exceed the public session, tutor or SMS limits. The session route allows 10 requests per second per connecting IP with a burst of 100; the tutor route allows 10 per second with a burst of 50. Tutor requests have a separate total concurrency cap of eight per nginx instance, subject to final proxy configuration. Browser CORS preflight requests do not consume these route-specific budgets. A live SMS service requires Redis: an atomic 60-second cooldown applies per canonical mainland China mobile number across backend workers, and Redis failures stop SMS delivery. The SMS proxy budget is five per minute per connecting IP with a burst of five. These are starting values: test them against a shared campus IP, model capacity and real SMS traffic before inviting a class. Multiple nginx instances each have their own counters and concurrency cap; a provider-side SMS spend cap remains advisable.

Every tutor turn returns a `GROUNDED` status with at least one source citation, or `INSUFFICIENT EVIDENCE` with a clarifying request. Only reviewed safe chunks are retrieved during scaffolding. The teaching stage, mastery, assessment lock, source list and output gate run on the backend. A locally configured model can propose a response and a separate model pass checks it; deterministic checks can still replace unsafe output. With no trusted explanation grader, the system keeps the explain-back gate closed rather than guessing at mastery. English/Chinese language choice is sent each turn. Reduced-motion settings, keyboard controls, text alternatives and mobile layouts are included in the web page.

## Acceptance and known limits

The supplied code and automated tests demonstrate the main flows but **do not certify all of the table's acceptance conditions in your environment**. Before production, test with the actual approved models, teaching files, network and institutional policies:

- **Five-minute indexing:** processing is async with restart recovery, but an unavailable embedding service, large files and an overloaded server can exceed five minutes. Measure the 50 MiB worst case; use a durable worker queue and capacity/timeout monitoring if that SLA is mandatory.
- **Bilingual retrieval and glossary consistency:** run a client-provided English↔Chinese question set and calculate Recall@5 (specification target ≥80%), plus glossary term consistency (target ≥90%). The lexical prototype setting is for development only and does not establish either target.
- **Answer quality:** review source relevance, explanation after genuine explain-back, assessment leakage, and injection attempts using representative staff prompts. The restricted fallbacks prioritize safe withholding; they may under-answer. Staff review of chunk categories is mandatory before activation.
- **Document references:** PDF page numbers are extracted from text pages; DOCX, TXT and MD use section indices, because these formats have no reliable fixed printed page. PowerPoint/slides are outside the accepted upload formats in this release.
- **PDF parser resources:** BRIDGE and legacy course PDFs are parsed by a separate `pypdf` process with a 70-second wall timeout, a 50 MiB input ceiling, and caps on pages and extracted text. Linux also applies CPU and memory limits. A failed or timed-out BRIDGE PDF shows a failed processing status. These are resource ceilings, not a filesystem sandbox; keep the upload endpoint restricted to authorised teaching staff.
- **Traffic and cost:** test the nginx rate and concurrency settings with the anticipated class size, institution model service and campus network address translation. A provider-side daily SMS spending cap and monitoring are still required to bound sends to many distinct phone numbers. The anonymous web token is kept in browser local storage; evaluate a tested Content Security Policy with the existing frontend before adding one.
- **Accessibility and privacy:** keyboard and reduced-motion support are implemented; independent mobile, screen-reader, WCAG 2.1 AA, GDPR and PIPL reviews and institutional sign-off are still required. Hosting locations and legacy non-BRIDGE integrations require separate review.
- **Minerva and WeChat:** deliberately omitted. They must use this same guarded tutor endpoint with trusted server-side assessment context if added later.

Run local checks from the project root with `PYTHONPATH=backend python -m pytest -q backend/tests` and `cd frontend && npm ci && npm run build`. Configure a test database as appropriate; do not put a production `.env` or source documents into the test ZIP.

## Small ECS model deployment and switching

The optional `ollama` Compose profile is for a small pilot. Its defaults cap the
service at two CPU cores and 4 GiB memory, with one parallel inference request,
two loaded models and a four-request queue. No model port is published publicly.
These caps protect the website; they are not evidence of capacity for hundreds
of concurrent students.

For the container deployment, run `docker compose --profile ollama up -d ollama`,
then use `docker compose exec ollama ollama pull qwen2.5:1.5b` and
`docker compose exec ollama ollama pull bge-m3`. Configure:

```dotenv
BRIDGE_PROVIDER=ollama
BRIDGE_LLM_URL=http://ollama:11434
BRIDGE_LLM_MODEL=qwen2.5:1.5b
BRIDGE_EMBEDDINGS_URL=http://ollama:11434/api/embed
BRIDGE_EMBEDDINGS_MODEL=bge-m3
BRIDGE_LLM_TIMEOUT_SECONDS=12
BRIDGE_TURN_TIMEOUT_SECONDS=35
```

If the official container image cannot be pulled, an existing host Ollama service
can be used instead. Find this project's bridge gateway with
`docker network inspect ta-platform_default --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'`.
Bind Ollama only to that private gateway, set the same queue and model limits, and
apply `CPUQuota=200%`, `MemoryHigh=3G`, `MemoryMax=4G` in its systemd override.
Order the service after Docker. Use that gateway in both URLs above. Do not use
`0.0.0.0` or open TCP 11434 in the ECS security group. Recheck the address if the
Docker network is recreated. Set `OLLAMA_NO_CLOUD=1` for this local-only service.

To use DeepSeek generation, edit only these server-side settings, keeping the
embedding URL and model unchanged:

```dotenv
BRIDGE_PROVIDER=deepseek
BRIDGE_DEEPSEEK_BASE_URL=https://api.deepseek.com
BRIDGE_DEEPSEEK_MODEL=deepseek-chat
```

Set a valid `DEEPSEEK_API_KEY` privately on the server, then rebuild/recreate the
backend with `docker compose up -d --no-deps --build backend`. Reload Nginx after
the backend is healthy so its upstream address is refreshed. Switching back only
requires `BRIDGE_PROVIDER=ollama` and another backend recreation. This is an
explicit provider choice, with no automatic transmission to a second provider
on errors. DeepSeek receives question text and the retrieved source excerpts;
local embeddings remain necessary for ingestion and retrieval.

Each model call has a configurable wall timeout (1–30 seconds); the whole tutor
turn has a separate 5–40 second deadline, default 35. A timed-out turn rolls back
its pending learning-state changes and returns HTTP 503 with `Retry-After`.
Missing credentials, provider errors, invalid/empty JSON and truncated model
output are rejected. Existing deterministic safety checks remain in force.

Before inviting students, use a separate test module to verify a real document
reaches `ready`, review its safe chunks, and check English and Chinese tutor
replies. Record latency and RAM usage. A passing provider contract test does not
establish real model quality, API quota, campus load capacity or course readiness.
