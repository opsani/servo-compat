FROM opsani/servox:v0.10.7
# note: keep the servox version equal to the one in pyproject.toml

ENV POETRY_CACHE_DIR='/var/cache/pypoetry'

# allow release to be optionally defined as a build arg
# nb: define here to avoid unnecessary rebuilds on change
ARG VERSION=0.0.0
ARG COMMIT=unknown
ARG TIMESTAMP=unknown

LABEL org.opencontainers.image.title="servo-compat" \
      org.opencontainers.image.description="Compatibility plugins for ServoX" \
      org.opencontainers.image.vendor="Opsani" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${COMMIT}" \
      org.opencontainers.image.created="${TIMESTAMP}"

WORKDIR /servo/servo_compat
COPY poetry.lock pyproject.toml README.md ./

# cache dependency install (without full sources)
RUN pip install poetry==1.1.* \
  && poetry install \
  $(if [ "$SERVO_ENV" = 'production' ]; then echo '--no-dev'; fi) \
    --no-interaction

# copy the full sources
COPY . ./

# install
RUN poetry install \
  $(if [ "$SERVO_ENV" = 'production' ]; then echo '--no-dev'; fi) \
    --no-interaction \
  # Clean poetry cache for production
  && if [ "$SERVO_ENV" = 'production' ]; then rm -rf "$POETRY_CACHE_DIR"; fi

# reset workdir for servox entrypoints
WORKDIR /servo
