ARG BUILD_FROM
FROM ${BUILD_FROM}

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends netcat-traditional curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /
COPY pyproject.toml /
RUN uv sync

# The fix: patch the pinned upstream package (fails the build if it no longer matches)
COPY patch_stt.py /tmp/patch_stt.py
RUN uv run python /tmp/patch_stt.py && rm /tmp/patch_stt.py

# s6 services, built here so the repo holds only plain files (GitHub web upload drops folders and exec bits)
COPY microsoft_run.sh microsoft_finish.sh discovery_run.sh /tmp/s6/
RUN d=/etc/s6-overlay/s6-rc.d \
    && mkdir -p $d/microsoft/dependencies.d $d/discovery/dependencies.d $d/user/contents.d \
    && printf longrun > $d/microsoft/type \
    && printf oneshot > $d/discovery/type \
    && mv /tmp/s6/microsoft_run.sh $d/microsoft/run \
    && mv /tmp/s6/microsoft_finish.sh $d/microsoft/finish \
    && mv /tmp/s6/discovery_run.sh $d/discovery/run \
    && printf /etc/s6-overlay/s6-rc.d/discovery/run > $d/discovery/up \
    && touch $d/microsoft/dependencies.d/base $d/discovery/dependencies.d/microsoft \
             $d/user/contents.d/microsoft $d/user/contents.d/discovery \
    && chmod a+x $d/microsoft/run $d/microsoft/finish $d/discovery/run $d/discovery/up

HEALTHCHECK --start-period=10m \
CMD echo '{ "type": "describe" }' \
    | nc -w 1 localhost 10300 \
    | grep -q "microsoft" \
    || exit 1
