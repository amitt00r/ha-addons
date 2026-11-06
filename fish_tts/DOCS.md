# Fish TTS

Wyoming TTS server for [Fish Audio](https://fish.audio) voices. Calls the Fish API directly, so it can
use the free `s2.1-pro-free` model, which HA's built-in Fish Audio integration does not offer.

1. Put your Fish API key in the configuration and list your voices (`name` + 32-character voice id
   from a `fish.audio/app/m/<id>` link).
2. Start the add-on. Home Assistant discovers it: accept the **Wyoming Protocol** integration.
3. In a voice assistant, pick **fish-tts** as text-to-speech and the voice by name.

Streaming: replies are spoken sentence by sentence as the conversation agent writes them.
Free model limits: fair use. Set `fallback_model` (e.g. `s2-pro`) to keep talking on paid credit when
the free model refuses a request.
