# pr1-ruff-fix

**적용 단계**: [실습 2] ① Issue #1 브랜치 두 번째 커밋 (`scripts/lab2_ci_protection.sh`)  
**연관 Issue**: Issue #1 (`issues/1-ci.md`)

---

## 폴더 개요
`pr1-ci-setup` 적용 후 처음 로컬에서 Ruff 린터를 실행했을 때 검출되는 **6건의 린트 에러 및 커버리지 범위를 수정한 파일 모음**입니다.

---

## 주요 수정 내용 및 파일 설명

| 파일 경로 | 수정 내용 및 목적 |
| :--- | :--- |
| **`backend/main.py`** | 린트 에러 수정:<br>- 미사용 import 제거<br>- 포맷팅 및 빈 줄 규칙 준수<br>- (참고: mimetypes 등록 후 import 순서로 인한 E402는 의도된 순서이므로 설정에서 예외 처리) |
| **`backend/pyproject.toml`** | Ruff 및 Coverage 설정 보완:<br>1. `[tool.ruff.lint.per-file-ignores]`: `src/main.py` 파일에 대해 E402(모듈 레벨 import 순서) 규칙 예외 적용<br>2. `[tool.coverage.run]`: 단위 테스트 대상이 아닌 MySQL 연동 코드(`src/persistence/mysql.py`)를 커버리지 측정 대상에서 제외(`omit`) |
| **`backend/spec/routes/test_updateItem.py`** | 테스트 코드 내 Ruff 린트 위반 사항 수정 |

