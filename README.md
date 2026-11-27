# pr3-filter

**적용 단계**: [실습 3] ① Issue #3 브랜치 커밋 (`scripts/lab3_feature_conflict.sh`)  
**연관 Issue**: Issue #3 (`issues/3-feat.md`) / PR #7

---

## 폴더 개요
클라이언트에서 할 일 목록을 상태별로 나누어 볼 수 있도록, **완료 여부(`?completed=true|false`)로 아이템을 필터링하는 백엔드 API 기능**과 해당 기능을 검증하는 단위 테스트 모음입니다.

---

## 주요 변경 사항 및 파일 설명

| 파일 경로 | 변경 내용 및 목적 |
| :--- | :--- |
| **`backend/src/routes/items.py`** | `GET /api/items` 및 `GET /items` 라우터 함수에 선택적 쿼리 파라미터 `completed: Optional[bool] = None` 추가:<br>- `?completed=true`: 완료된 항목만 반환<br>- `?completed=false`: 미완료된 항목만 반환<br>- 생략 시: 전체 항목 반환 (기존 동작 유지) |
| **`backend/spec/routes/test_filterItems.py`** | **[신규 테스트 추가]** 필터링 요구사항 4가지를 검증하는 단위 테스트:<br>1. `completed=true` 필터링 검증<br>2. `completed=false` 필터링 검증<br>3. 파라미터 생략 시 전체 반환 검증<br>4. 잘못된 파라미터 값(`?completed=abc`) 입력 시 FastAPI 유효성 검사 에러(422) 검증 |

