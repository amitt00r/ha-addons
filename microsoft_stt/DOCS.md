# Microsoft STT (fixed)

Microsoft Azure speech to text over Wyoming. A copy of
[hugobloem's Microsoft STT add-on](https://github.com/hugobloem/homeassistant-addons/tree/main/microsoft-stt)
(Apache-2.0, `wyoming-microsoft-stt` 1.3.10) with one fix applied at build time (`patch_stt.py`):

- **Stale transcripts.** Upstream returns the *previous* request's text whenever Azure recognises
  nothing (silence, noise, a cut-off recording), so the voice assistant answers the last question
  again. Each request now starts empty.
- Speech with a pause in it is returned whole (upstream kept only the last segment).

Other changes: Debian bookworm base (bullseye mirrors 404); the s6 service files are created in the Dockerfile; `subscription_key` is a password field;
`update_languages` defaults to off (the locales download returns 401 with a Speech key and falls back to the bundled list).

Setup: enter the Azure Speech key, region (e.g. `centralindia`) and language (e.g. `en-IN`; several separated
by `;`), start the add-on and accept the discovered **Wyoming Protocol** integration.
