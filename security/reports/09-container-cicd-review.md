# Container And CI/CD Review

## Docker

- `Dockerfile` uses `nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04`, not `latest`.
- Container appears to run as root by default; no `USER` directive found.
- No `HEALTHCHECK`, read-only filesystem, dropped capabilities, or `no-new-privileges` found.
- `docker-compose.yml` mounts `./inputs`, `./outputs`, and a named cache volume into the container.
- Image name `ats-lipsync:latest` is local; base image is pinned by tag but not digest.

## CI/CD

- No `.github` workflow directory found.
- No SAST/dependency/secret scan pipeline was found.

## Recommendations

- Add non-root user, least-privilege filesystem mounts, resource limits, and image digest pinning.
- Add CI jobs for tests, `npm audit`, `pip-audit`, secret scanning, and Docker scanning.
