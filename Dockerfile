###################################################
# Todo 앱 멀티스테이지 Dockerfile (React + FastAPI + Claude AI)
#
# 스테이지 구성
#   base → client-base ─┬→ client-dev     (개발: Vite 개발 서버)
#                       └→ client-build   (React 정적 파일 빌드)
#   backend-base → backend-deps ─┬→ backend-dev → test   (개발 / pytest)
#                                └→ final                (운영: 백엔드 + 정적 파일)
#
# 사용처
#   compose.yaml            : client-dev, backend-dev
#   compose-prod-build.yml  : final
#   테스트 실행              : docker build --target test .
###################################################

###################################################
# Stage: base
#
# 모든 클라이언트 스테이지가 같은 베이스 이미지를 쓰도록 하고,
# 작업 디렉터리 등 공통 설정을 제공한다.
#
# node:22 대신 node:22-slim 을 쓰는 이유: 전체 이미지에는 앱이 필요로 하지
# 않는 오래된 PostgreSQL 라이브러리(postgresql-15)가 들어 있고, 여기에
# 수정 가능한 높은 심각도의 CVE 가 있다. 또한 이미지에 포함된 npm 의 의존
# 패키지(brace-expansion, pacote 등)에 취약점이 있어 npm 을 최신으로 올린다.
###################################################
FROM node:22-slim AS base
RUN npm install -g npm@latest && npm cache clean --force
WORKDIR /usr/local/app

################## CLIENT STAGES ##################

###################################################
# Stage: client-base
#
# client-dev 와 client-build 가 공통으로 쓰는 스테이지.
# package*.json 만 먼저 복사해 npm ci 레이어를 캐시하고,
# 소스(src)는 마지막에 복사해 코드만 바뀌면 의존성 설치를 건너뛴다.
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
# 클라이언트 개발용. Vite 개발 서버(5173 포트, HMR)를 시작한다.
# compose.yaml 의 develop.watch 가 ./client/src 를 이 컨테이너로 sync 한다.
###################################################
FROM client-base AS client-dev
EXPOSE 5173
CMD ["npm", "run", "dev"]

###################################################
# Stage: client-build
#
# React 앱을 정적 HTML/CSS/JS(dist/)로 빌드한다. (tsc 타입 검사 + vite build)
# 결과물은 final 스테이지에서 백엔드의 src/static 으로 복사되어 서빙된다.
#
# 참고: package.json 의 build 스크립트 마지막 단계(copy-build.js)는 로컬
# 개발 환경에서 dist 를 ../backend/src/static 으로 복사하는 용도이며,
# 컨테이너에서는 의미가 없다. 실제 복사는 final 스테이지의 COPY --from 이 한다.
###################################################
FROM client-base AS client-build
RUN npm run build




###################################################
################  BACKEND STAGES  #################
###################################################

###################################################
# Stage: backend-base
#
# FastAPI 백엔드용 Python 베이스 이미지. 모든 백엔드 스테이지가 공유한다.
#
# - SQLite 드라이버(aiosqlite)는 파이썬 표준 라이브러리 sqlite3 를 쓰고,
#   PostgreSQL 드라이버(asyncpg)와 Anthropic SDK 는 wheel 로 설치되므로
#   별도의 네이티브 빌드 도구가 필요 없다.
# - PYTHONDONTWRITEBYTECODE: .pyc 파일을 만들지 않는다.
# - PYTHONUNBUFFERED: 로그를 버퍼링 없이 즉시 출력한다 (docker logs 용).
###################################################
FROM python:3.14-slim AS backend-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# 최신 OS 보안 패치를 반영하고, 이미지에 들어 있는 pip/setuptools 를 올린다.
# (pip 이 내장한 urllib3/msgpack 에 자체 CVE 가 있다.)
RUN apt-get update && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip setuptools
WORKDIR /usr/local/app

###################################################
# Stage: backend-deps
#
# requirements.txt 의 파이썬 의존성만 설치한다 (fastapi, uvicorn, asyncpg,
# aiosqlite, anthropic 등 운영 의존성). backend-dev 와 final 의 공통 베이스다.
# 이 파일만 먼저 복사하므로 requirements.txt 가 바뀌기 전까지 레이어가 캐시된다.
###################################################
FROM backend-base AS backend-deps
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

###################################################
# Stage: backend-dev
#
# 백엔드 개발 및 테스트용. 테스트 패키지(pytest 등)는 requirements-dev.txt 에
# 있으므로 여기서 추가로 설치한다 (final 이미지에는 들어가지 않음). main.py 는 uvicorn 을 reload=True 로
# 실행하므로, compose.yaml 의 develop.watch 가 ./backend/src 를 sync 하면
# 서버가 자동으로 다시 시작된다.
#
# 환경변수 (compose 에서 주입)
#   POSTGRES_HOST/USER/PASSWORD/DB : 있으면 PostgreSQL, 없으면 SQLite 사용
#   ANTHROPIC_API_KEY              : 있으면 Claude 자동 분류 활성화
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
# 백엔드 pytest(spec/: routes, persistence, ai)를 실행한다. final 이미지에
# 테스트 코드가 들어가지 않도록 별도 스테이지로 분리했다.
# 테스트는 외부 DB 나 Claude API 없이 돌아가야 한다 (SQLite, AI 모킹).
###################################################
FROM backend-dev AS test
RUN python -m pytest

###################################################
# Stage: final
#
# 운영용 최종 이미지. FastAPI 백엔드에 client-build 의 React 빌드 결과(dist)를
# src/static 으로 복사해 한 이미지로 묶는다. main.py 가 이 디렉터리가 있으면
# StaticFiles 로 서빙한다 (/api/* 는 API, 그 외 경로는 React 앱).
# 개발용과 달리 --reload 없이 uvicorn 으로 직접 실행한다.
#
# test 스테이지에서 pytest.ini 를 복사하는 이유: 이 COPY 가 없으면 final 만
# 빌드할 때 test 스테이지가 건너뛰어져 테스트가 실행되지 않는다.
# (테스트가 실패하면 final 이미지 빌드도 실패한다.)
###################################################
FROM backend-deps AS final
COPY --from=test /usr/local/app/pytest.ini ./
COPY backend/src ./src
COPY --from=client-build /usr/local/app/dist ./src/static
EXPOSE 3000
# 컨테이너 상태 확인: /api/greeting 이 200 을 돌려주면 정상 (추가 패키지 불필요)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3000/api/greeting', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3000"]
