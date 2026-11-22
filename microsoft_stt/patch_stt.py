"""Fix wyoming-microsoft-stt 1.3.10 returning the previous transcript.

Upstream keeps the last recognised result in self._results and never clears it, so a request in
which Azure recognises nothing (silence, noise, a cut-off recording) returns the previous
request's text. Each request now collects its own results; all recognised segments are joined
(upstream kept only the last segment, dropping the start of anything said with a pause).
Azure cancellations are logged with their reason (upstream logged them only in debug, without it).
"""

import pathlib

import wyoming_microsoft_stt.microsoft_stt as mod

path = pathlib.Path(mod.__file__)
src = path.read_text()

EDITS = [
    (
        """        self._speech_recognizer.canceled.connect(
            lambda evt: _LOGGER.debug(f"CANCELED {evt}")
        )
""",
        """        def canceled(evt):
            details = evt.cancellation_details
            _LOGGER.warning(
                "Azure canceled recognition: reason=%s code=%s details=%s",
                details.reason, details.code, details.error_details,
            )

        self._speech_recognizer.canceled.connect(canceled)
""",
    ),
    (
        """        def recognized(event: speechsdk.SpeechRecognitionEventArgs):
            _LOGGER.debug(f"{event.result}")
            self._results = event.result
""",
        """        results = []  # this request only: late events from an old recognizer cannot leak in
        self._results = results

        def recognized(event: speechsdk.SpeechRecognitionEventArgs):
            _LOGGER.debug(f"{event.result}")
            results.append(event.result)
""",
    ),
    (
        """            if self._results is None:
                _LOGGER.debug("No results from transcription.")
                return ""

            return self._results.text
""",
        """            texts = [
                r.text
                for r in (self._results or [])
                if r.reason == speechsdk.ResultReason.RecognizedSpeech and r.text
            ]
            self._results = None
            if not texts:
                _LOGGER.debug("No results from transcription.")
                return ""

            return " ".join(texts)
""",
    ),
]

for old, new in EDITS:
    if src.count(old) != 1:
        raise SystemExit(f"patch_stt: upstream code changed, cannot apply:\n{old}")
    src = src.replace(old, new)

path.write_text(src)
print(f"patch_stt: patched {path}")
