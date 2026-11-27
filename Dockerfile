###################################################
# Stage: base
#
# This base stage ensures all other stages are using the same base image
# and provides common configuration for all stages, such as the working dir.
#
# node:22-slim is used instead of node:22 because the full image bundles an
# outdated PostgreSQL library (postgresql-15) that the app does not need and
# that has fixable high-severity CVEs. npm is upgraded because the npm bundled
# with the image has vulnerable dependencies (brace-expansion, pacote, ...).
###################################################
FROM node:22-slim AS base
RUN npm install -g npm@latest && npm cache clean --force
WORKDIR /usr/local/app

################## CLIENT STAGES ##################

###################################################
# Stage: client-base
#
# This stage is used as the base for the client-dev and client-build stages,
# since there are common steps needed for each.
###################################################
FROM base AS client-base
COPY client/package.json client/package-lock.json ./
COPY .npmrc .
RUN npm ci
COPY client/.eslintrc.cjs client/index.html client/vite.config.ts ./
COPY client/tsconfig.json client/tsconfig.app.json client/tsconfig.node.json ./
COPY client/copy-build.js ./
COPY client/public ./public
COPY client/src ./src

###################################################
# Stage: client-dev
#
# This stage is used for development of the client application. It sets
# the default command to start the Vite development server.
###################################################
FROM client-base AS client-dev
CMD ["npm", "run", "dev"]

###################################################
# Stage: client-build
#
# This stage builds the client application, producing static HTML, CSS, and
# JS files that can be served by the backend.
###################################################
FROM client-base AS client-build
RUN npm run build




###################################################
################  BACKEND STAGES  #################
###################################################

###################################################
# Stage: backend-base
#
# This stage is the Python base image for the FastAPI backend. Its common
# steps are shared by every backend stage.
#
# Note: the sqlite3 driver (aiosqlite) uses Python's standard library sqlite3
# module, so there is no native build step as there was for the old Node
# backend.
###################################################
FROM python:3.14-slim AS backend-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# Pick up the latest OS security fixes and upgrade the pip/setuptools bundled
# in the image (pip vendors urllib3/msgpack, which carry their own CVEs).
RUN apt-get update && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip setuptools
WORKDIR /usr/local/app

###################################################
# Stage: backend-deps
#
# Installs only the runtime Python dependencies from requirements.txt. This is
# the base for the final production image, so it has no test packages. Only
# this file is copied first, so the layer is cached until requirements change.
###################################################
FROM backend-base AS backend-deps
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

###################################################
# Stage: backend-dev
#
# This stage is used for development and testing of the backend. It adds the
# test dependencies from requirements-dev.txt (which includes requirements.txt)
# and runs main.py, which starts uvicorn with --reload enabled.
###################################################
FROM backend-deps AS backend-dev
COPY backend/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY backend/main.py backend/pytest.ini ./
COPY backend/spec ./spec
COPY backend/src ./src
EXPOSE 3000
CMD ["python", "main.py"]

###################################################
# Stage: test
#
# This stage runs the pytest suite on the backend. This is split into a
# separate stage to allow the final image to not have the test cases.
###################################################
FROM backend-dev AS test
RUN python -m pytest

###################################################
# Stage: final
#
# This stage is intended to be the final "production" image. It sets up the
# FastAPI backend and copies the built client application from the client-build
# stage. The application is served by uvicorn without --reload.
#
# It copies pytest.ini from the test stage to ensure that the tests run
# (without this, the test stage would simply be skipped).
###################################################
FROM backend-deps AS final
COPY --from=test /usr/local/app/pytest.ini ./
COPY backend/src ./src
COPY --from=client-build /usr/local/app/dist ./src/static
# 비루트 사용자로 실행 (Kubernetes runAsNonRoot 대응) — SQLite 기본 경로 /etc/todos 도 넘겨 줌
RUN useradd --uid 10001 --create-home app \
    && mkdir -p /etc/todos && chown app:app /etc/todos
USER 10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/api/greeting', timeout=2)" || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3000"]
