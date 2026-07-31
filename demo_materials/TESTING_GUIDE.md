# Deployment test guide

Use these materials after your Render backend and Vercel frontend are live.

## Before testing

1. Open `https://YOUR-RENDER-URL/health`.
2. Confirm `status` is `ok` and `gemini_key_configured` is `true`.
3. Open `https://YOUR-RENDER-URL/docs`.
4. In `POST /ingest`, click **Try it out** and submit the contents of `company_operations_handbook.md` with source `company_operations_handbook.md`.
5. Confirm the response reports one or more ingested chunks.

## Run the test matrix

Ask each question from `test_questions.json` in the Vercel application. For each test, record:

| ID | Pass rule |
| --- | --- |
| T01 | Answer says 4 and trace contains `data(sql)` and critic. |
| T02 | Answer says Missing integration. |
| T03 | Answer says 3. |
| T04–T07 | Answer includes the expected handbook fact and shows a retriever step/source. |
| T08 | Answer combines the database count and a handbook policy; trace should include data and retrieval. |
| T09 | It must say the release date is unknown/not committed, not invent one. |
| T10–T11 | Use the same `session_id` through `/docs` or browser session; T11 should recall Nadia Karimova. |

For a passing answer, the trace must end in a critic step. Save a screenshot of T08's trace and answer for your capstone evidence.

## Optional web-agent test

Only if `TAVILY_API_KEY` is configured in Render, ask a current-events question such as `What is today's top AI news headline?`. The trace should include `web`. Do not expect this test to pass without Tavily.

## Automated API smoke test

From PowerShell, run this from the repository root after replacing the URL:

```powershell
.\demo_materials\run_deployed_smoke_tests.ps1 -ApiUrl "https://YOUR-RENDER-URL"
```

The script checks health, ingests the handbook, and sends the core SQL and RAG questions to `/chat`. It prints each answer, sources, and agent steps.
