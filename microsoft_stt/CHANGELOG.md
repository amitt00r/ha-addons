## 1.3.10.2

- Log why Azure cancels a recognition (reason, error code, details) as a warning.
- Build on Debian bookworm (bullseye security mirror 404s).

## 1.3.10.1

- Based on upstream Microsoft STT 1.3.10.
- Fix: a request with no recognised speech no longer returns the previous request's transcript.
- Fix: all recognised segments are returned, not just the last one.
