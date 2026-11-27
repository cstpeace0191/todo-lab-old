# pr2-docker-fix

**적용 단계**: [실습 2] ④ Issue #2 브랜치 커밋 (`scripts/lab2_ci_protection.sh`)  
**연관 Issue**: Issue #2 (`issues/2-bug.md`) / PR #5

---

## 폴더 개요
새로 clone한 환경에서 도커 빌드가 실패하던 버그(누락된 `requirements-dev.txt`)를 수정하고, 프로덕션 컨테이너 이미지의 보안(비루트 실행)과 안정성(HEALTHCHECK)을 강화하기 위한 파일 모음입니다.

---

## 주요 변경 사항 및 파일 설명

| 파일 경로 | 변경 내용 및 목적 |
| :--- | :--- |
| **`Dockerfile`** | 컨테이너 빌드 및 보안 강화:<br>1. `requirements-dev.txt` 파일을 컨테이너 내부로 올바르게 복사하도록 빌드 단계 수정<br>2. 최종 운영 이미지(`target: final`)를 루트(root) 대신 **비루트 사용자(`USER 10001`)**로 실행하도록 보안 강화<br>3. 컨테이너 헬스체크(`HEALTHCHECK`) 추가 (`/api/greeting` 엔드포인트 헬스체크) |
| **`backend/requirements-dev.txt`** | **[신규 추가]** 테스트 및 개발에만 필요한 패키지(`pytest`, `pytest-asyncio`, `httpx`, `pytest-cov`, `ruff`)를 정의하여 운영 이미지에 불필요한 테스트 패키지가 포함되지 않도록 분리 |
| **`backend/requirements.txt`** | 운영 런타임에 꼭 필요한 패키지(`fastapi`, `uvicorn`, `aiomysql`, `aiosqlite`)만 남기도록 경량화 |
| **`.github/workflows/ci.yml`** | CI 워크플로의 backend 의존성 설치 단계를 `requirements-dev.txt` 기준으로 설치하도록 업데이트 |

