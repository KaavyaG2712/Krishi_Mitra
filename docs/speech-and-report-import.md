# Speech fix and soil-report import

Updated 27 September 2026. This follows the original soil/voice implementation.

## What caused the speech failure

The old button depended entirely on `window.SpeechRecognition` / `webkitSpeechRecognition`. Its constructor may exist even when the browser's remote recognition service is unavailable. The screenshot's exact message mapped to the `network` recognition error. Retrying invoked the same failing service, and the message incorrectly implied that ordinary internet access was the problem. Browser logs also showed `speech_recognition_failed`. See [MDN's explanation of server-based recognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).

The default now uses `getUserMedia` and `MediaRecorder`, converts the recording to mono 16 kHz PCM WAV, and sends it to the app's `/api/v1/speech/transcribe` endpoint. Gemini transcribes only; the farmer sees and can edit the original-language transcript before sending a chat question. Translation and the existing advisor flow remain separate. [Gemini supports audio transcription](https://ai.google.dev/gemini-api/docs/audio).

The browser speech path remains selectable, with a specific provider-failure message. There is no hidden switch that sends the same recording to a second provider. Server status is checked before asking for microphone permission. Stop submits the recording; Cancel discards it. Automatic stop occurs after 30 seconds. Cancellation also stops a microphone whose permission request finishes late, and suppresses late transcripts. Switching languages or leaving the screen cancels the session.

### Speech setup and privacy

1. Set the existing `GEMINI_API_KEY` in **backend/.env**, then restart the backend. Never put it in a frontend variable or paste it into the chat UI.
2. By default, speech uses `GEMINI_GENERATION_MODEL`. Set `GEMINI_SPEECH_MODEL` to an audio-capable model available in the account if a separate model is needed.
3. Open the frontend on localhost or HTTPS. A plain HTTP LAN IP generally cannot access browser microphones.
4. In the advisor, leave **Server recording (recommended)** selected. Tap to Speak, allow the microphone, speak, tap Stop, check the transcript, then Send.

The key belongs to the application owner, not each farmer. This worktree initially had no `.env`. The original checkout's existing backend configuration was subsequently found and loaded using Uvicorn's `--env-file` option, without displaying or copying the key. A real request through `/speech/transcribe` returned HTTP 200 and correctly transcribed a locally synthesized English test recording, including pH 7.1. That verifies provider connectivity and the real HTTP/audio contract. Physical microphone capture and Hindi/Tamil/Telugu recognition accuracy on farmer recordings remain device/field acceptance tests. The missing-key state is also explicit and covered by tests.

When running an isolated worktree, you can reuse an existing backend configuration explicitly:

```powershell
# From this worktree's backend directory; use your existing checkout's actual path.
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file "C:/path/to/existing-checkout/backend/.env"
```

This is a launch option, not a committed secret or an automatic search for credentials outside the project. Make sure `FRONTEND_ORIGINS` matches the frontend address you use.

Audio travels to this backend and Google Gemini using the application's provider account. The UI discloses that before recording. This app stores neither audio files nor raw-audio logs; provider data handling follows the account's Gemini terms. The endpoint accepts only bounded, valid mono 16 kHz/16-bit WAV data, validates duration and frame completeness, rejects oversized uploads, and applies existing request quotas. Calls have finite timeouts and no automatic paid retry. Normal chat storage remains unchanged.

## Soil data without a public government key

The [public Soil Health Card page](https://soilhealth.dac.gov.in/soilhealthcard) was inspected. Its farmer search uses phone number or farmer name and a CAPTCHA. We did not submit personal information, solve the CAPTCHA, or call undocumented internal APIs. Registered API access can remain an optional deployment integration; it is no longer the main farmer workflow.

The implemented alternative is **import once, review, save, reuse**:

1. Obtain the farmer's existing Soil Health Card PDF, photograph the paper lab report, or copy results text. The official portal is linked so the farmer can complete its own access steps.
2. Choose **Scan or import your soil report**. Upload a JPG, PNG, WebP or PDF, or use **Paste report text instead**.
3. Review extracted rows and the original image/PDF. Clear rows populate the existing soil form; unknown or ambiguous data remains blank. Review/correct the form and explicitly confirm comparison with the original report.
4. Optionally choose **Save as a reusable report on this device**, provide a field/report name, and submit. The next visit shows **Saved soil reports**. Choosing one restores its values and test date without typing them again. Submitting validates them again and issues a fresh signed profile.
5. Delete individual reports on shared devices. A new soil test should replace old information when appropriate; a saved report is not today's live measurement.

No API key is needed for report import, OCR, saved-report reuse, or manual soil normalization. A farmer still needs at least one actual soil test/report; GPS and a photo of bare soil cannot supply trustworthy laboratory measurements.

### Local processing and constraints

- PDF text extraction uses PDF.js. Image reports and scanned PDFs use Tesseract.js in a worker. Worker code, WASM and English model data are served by this app, not fetched from an OCR provider. The document stays in the browser; only reviewed numeric values are submitted to the backend.
- OCR assets are prepared from locked npm packages by `scripts/prepare-ocr.mjs` during install/dev/build. `public/ocr/` is generated and ignored by Git. The complete built `dist/ocr/` must be deployed. These heavier assets load only when OCR is used. This does not add a complete offline/PWA mode.
- Limits: 10 MB per file, 25 megapixels per photo, 3 PDF pages, one sample at a time, 90-second UI timeout. Cancel stops the reader. A corrupt/encrypted/unsupported report leaves manual and pasted-text routes available.
- Best results require upright, clear printed English parameter names or chemical symbols. Hindi/Tamil/Telugu navigation does not imply those scripts are supported by the English OCR model. Handwriting, faint scans and unusual table layouts can require correction or manual entry.
- Extraction recognizes all 12 existing parameter keys. It never fills a missing parameter with zero or invents a unit. Ambiguous ranges, multiple numeric columns, duplicate parameter rows, damaged numeric fragments, comma decimals, unfamiliar units and different chemical bases such as P2O5/K2O are rejected for manual review. Only explicitly labelled ISO sample dates are auto-filled.
- Import cannot authenticate a government-issued document. Reviewed imports retain `USER_ENTERED` provenance and the ordinary soil-report source, never `GOVERNMENT_VERIFIED` or laboratory-certified OCR confidence.
- Up to 10 named reports are stored locally, only after opt-in. They contain editable values/units/date, a chosen name and save timestamp; no photo/PDF, full OCR text, location, account identifier or signed capability is stored. They are not encrypted or synchronized across devices, and browser storage clearing removes them. Existing optional draft storage is separate.

## Files and validation

New backend: `app/modules/advisor/transcription.py`, `app/api/v1/endpoints/speech.py`, `tests/test_speech_recording.py`. Routing, body-size middleware, settings and `.env.example` wire the service into the existing app.

New frontend: `services/recordedSpeech.ts`, `services/soilReport.ts`, `services/reportReader.ts`, `components/ReportImport.tsx`, `scripts/prepare-ocr.mjs`, `test/recordedSpeech.test.ts`, `test/report.test.tsx`. Existing Voice/SoilHealth components, localization, styles, npm manifests and docs were updated.

Validation includes backend malformed/overlong/truncated WAV rejection, language propagation, provider payload contract, missing-key and no-speech failures; frontend provider selection/cancellation/late permission cleanup, WAV upload, conservative extraction, mandatory review and named-report save/reuse/delete. Actual browser checks exercised image OCR, scanned-PDF OCR, reviewed values through the real API, and saved-report reuse after reload. These used clearly marked synthetic fixtures, not real farmer records or a field accuracy study. OCR errors in the pH row were caught during testing and added to regression coverage. The complete automated suites pass 60 backend tests and 29 frontend tests; TypeScript/production build and npm audit pass.
