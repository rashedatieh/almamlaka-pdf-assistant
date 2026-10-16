# Video kit: Almamlaka TV Bilingual PDF Knowledge Assistant

> **Prototype by Rashed Atieh for evaluation — not an official Almamlaka TV product.**
> نموذج أولي من إعداد راشد عطية لأغراض التقييم — ليس منتجاً رسمياً لقناة المملكة.

This folder has everything you need to record a 4–6 minute demo and explainer video for the Almamlaka TV
evaluators, both product and technical. Every number in these files names the repository file it comes from.
If a number on screen ever differs from the file it cites, trust the file and re-record the shot.

## What is in the kit

| File | Use it for |
|---|---|
| `README.md` | This page: setup, recording order, checks before you press record |
| `video-script.md` | The script, scene by scene, as VISUAL / VOICEOVER tables. The English voiceover comes first, then the full Modern Standard Arabic voiceover for the Arabic cut |
| `storyboard-shotlist.md` | Numbered shots with duration, screen, exact clicks and keystrokes, on-screen text overlays and B-roll ideas |
| `technical-brief.md` | 3–5 pages for the technical evaluator: architecture, each pipeline step and why, verification rules V1–V8, security, bilingual handling, results, cost, limitations |
| `requirements-matrix.md` | The nine requirements of the client brief, in its own words and order (R1–R9): how each is met, where in the code, which tests cover it, the live result, what to show |
| `faq-talking-points.md` | Short answers to the questions evaluators are likely to ask |
| `pipeline-graph.html` | The interactive pipeline graph for the architecture scene. It is built separately and placed in this folder |
| `screens/` | Still images for overlays and B-roll, if provided. They are built separately |

## Placeholders

| Placeholder | Where | Fill it from |
|---|---|---|
| `<INVITE_LINK>` | This README, the shot list | The reviewer link: the public URL followed by `/?invite=<token>`. The owner holds the token (`infra/08_deploy.sh`, step G3). **Never paste the real link into these files** |
| End-to-end results | Already filled in from `eval/reports/e2e/record.md` (the full run on the 48 gold questions) | If that run is repeated, update `video-script.md` scene 12, `storyboard-shotlist.md` shot 34, `technical-brief.md` §7, `requirements-matrix.md` and `faq-talking-points.md` from the new file |

## Before you record (15 minutes)

1. **Open the app with the invite link.** Open a fresh incognito window (`Ctrl+Shift+N` in Chrome or Edge)
   and paste `<INVITE_LINK>`. The server checks the token, sets an HttpOnly cookie and redirects to the
   clean URL, so the token disappears from the address bar (`app/server.py`, route `/`). The address bar
   then shows only the public URL, `https://almamlaka-assistant-383606437746.me-central1.run.app`, which is
   fine to show. **Start recording only after the redirect.** The token must never be on screen.
2. **Warm up the service.** Cloud Run scales to zero when idle (`infra/08_deploy.sh`: `--min-instances=0`),
   so the first request after a quiet spell is slow. Ask one throwaway question, such as
   `Who is the project lead for the Digital Expansion Initiative?`, then click **New conversation**.
3. **Check the two new features.** Click a citation number in that answer: the **Evidence spotlight** must
   open the real PDF page with the quote highlighted. Click **Executive report**: the dialog must show
   **Download PDF**. If either is missing, the live build is older than this kit. Redeploy or cut the scene.
4. **Mind the guards while you record.**
   - Rate limit: 10 questions per minute from one IP address (`RATE_LIMIT_PER_MIN=10`, `infra/08_deploy.sh`).
     Wait for each answer to finish before you type the next question.
   - Daily cap: $2.00 of Claude spend per UTC day (`DAILY_BUDGET_USD=2.00`, `infra/08_deploy.sh`; logic in
     `app/budget.py`). One run of the demo is about 10 turns. The measured cost is $0.0137 per turn
     (`eval/reports/e2e/record.md`, 48 questions), so a run costs about $0.14. You can rehearse several times.
   - The Executive report and its PDF are pre-generated, so opening them costs nothing
     (`app/pipeline/report.py`, ADR D24).
5. **Open the pipeline graph.** In a normal (non-incognito) window, double-click
   `video-kit/pipeline-graph.html`. It opens in your default browser and needs no internet. Press
   **Play the request** to animate one question through the pipeline, and click any step to open its
   explanation. Rehearse the click order in scene 9 of `video-script.md` once before recording.
6. **Rehearse each live beat once.** Model answers can vary slightly between runs, so ask each scripted
   question (scenes 2–7) once before recording, then click **New conversation**.

## Screen and browser settings

| Setting | Value |
|---|---|
| Recording resolution | **1920 × 1080**, 30 fps. Use 60 fps if your tool allows: the animated particle title looks smoother |
| Windows display scaling | 100%. If your laptop runs at 125–150%, set it to 100% for the recording, or record a 1920 × 1080 region |
| Browser | Chrome or Edge, full screen (`F11`), bookmarks bar hidden (`Ctrl+Shift+B`), no extension icons visible |
| Browser zoom | **110%** for the chat (`Ctrl` and `+`, `Ctrl+0` resets). **100%** for the Executive report, the downloaded PDF and `pipeline-graph.html` |
| Theme | Light theme (sun icon in the header) for the main take. One dark-theme B-roll shot is optional |
| Language | The app opens in Arabic (`web/src/App.tsx`, `initialLang`). Switch with the language button at the top of the header (it reads **English** or **العربية**) |
| Mouse | Turn on click highlighting in your recorder if it has it. Move slowly, and pause one second after each answer finishes |
| Notifications | Windows Focus Assist on. Close Slack, Teams and mail |

## Recording tools

- **OBS Studio** (free): add a Display Capture or Window Capture source on a 1920 × 1080 canvas, output MP4.
- **Windows Clipchamp**, or **Xbox Game Bar** (`Win+G`, then `Win+Alt+R` to start and stop), also work.
- Voiceover: record it separately in a quiet room with a USB or headset microphone, then lay it over the
  screen capture in Clipchamp, DaVinci Resolve or CapCut. Record the English and Arabic voiceovers as two
  tracks over the same screen capture, so one capture gives both cuts.

## Recording order (lowest risk first)

| Order | What | Why this order |
|---|---|---|
| 1 | Scene 9: architecture with `pipeline-graph.html` | Offline, costs nothing, no live dependency |
| 2 | Scene 8: Executive report and PDF download | Pre-generated, costs nothing |
| 3 | Scenes 2–7: the live demo, in script order, in one conversation | Each question is a paid live turn. Aim for one clean take. Scene 7 clicks a citation from scene 6 |
| 4 | Scenes 10–12: trust, cost, results | Code views and overlay cards under voiceover, no live calls |
| 5 | Scenes 0, 1 and 13: hook, product, close | Easiest to re-record once the rest is final |
| 6 | Voiceover tracks (EN, then AR) | Record them against the edited picture |

The wording of live answers can vary slightly between runs. That is expected: the checks hold the facts,
citations, statuses and flags constant, not the phrasing. If an answer comes back as an error or with a
different status from the script, click **New conversation** and ask again. Never edit an answer, or an
overlay, to hide what happened.

## What must never be on screen

- The invite token or `<INVITE_LINK>` itself, the Anthropic API key, the contents of the `app-secrets`
  secret, or any `.env` file.
- Google or Anthropic account e-mail addresses, billing account IDs or invoices. Blur them in any console B-roll.
- Any author credit other than the attribution "Prototype by Rashed Atieh for evaluation — not an official
  Almamlaka TV product". The app shows it in the navy strip under the header (`web/src/lib/i18n.ts`, `prototype`).

## Export

- MP4 (H.264 video, AAC audio), 1920 × 1080. Keep each file under 100 MB if it has to be attached to a form.
- Two files: `almamlaka-assistant-demo-EN.mp4` and `almamlaka-assistant-demo-AR.mp4`.
- Burn the attribution line into the first and last 5 seconds of both cuts.
