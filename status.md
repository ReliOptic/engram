# Engram — 프로젝트 현황 보고서

**기준일**: 2026-04-29  
**총 커밋**: 48개 (2026-04-12 ~ 현재)  
**브랜치**: master (clean)

---

## 실행 환경

| 서비스 | 주소 | 상태 |
|---|---|---|
| Frontend (Vite dev) | http://localhost:3001 | ✅ 실행 중 |
| Backend (FastAPI) | http://localhost:8000 | ✅ 실행 중 |
| ChromaDB | data/chroma_db/ | 파일 영속성 |
| SQLite | data/sqlite/engram.db | 파일 영속성 |

---

## 코드베이스 규모

| 영역 | 파일 수 | 코드 라인 |
|---|---|---|
| Backend (Python) | 109개 .py | ~4,600줄 |
| Frontend (React/TS) | 28개 .tsx/.ts | ~5,500줄 |
| Backend 테스트 | 35개 test_*.py | — |
| Frontend 테스트 | 2개 regression .test.ts | 7 tests |

---

## 구현 완료 모듈

### Backend

| 모듈 | 파일 | 상태 |
|---|---|---|
| FastAPI 앱 + WebSocket + REST API | backend/main.py | ✅ |
| 멀티에이전트 오케스트레이터 | backend/agents/orchestrator.py | ✅ |
| Analyzer / Finder / Reviewer 에이전트 | backend/agents/*.py | ✅ |
| LLM 클라이언트 (OpenRouter + OpenAI) | backend/utils/llm_client.py | ✅ |
| VectorDB 래퍼 (ChromaDB + 사일로 필터) | backend/knowledge/vectordb.py | ✅ |
| 케이스 레코더 (Type A/B 청크 자동 생성) | backend/memory/case_recorder.py | ✅ |
| 주간 보고서 파서 (Excel 이중 포맷) | backend/knowledge/weekly_ingester.py | ✅ |
| Dreaming 파이프라인 (Light/REM/Deep) | backend/knowledge/dreaming.py | ✅ |
| 중복 제거 (정확 + 의미적) | backend/knowledge/dedup.py | ✅ |
| 지식 그래프 (NetworkX) | backend/knowledge/graph.py | ✅ |
| SQLite 케이스 + 비용 추적 | backend/knowledge/database.py | ✅ |
| 묵시적 지식 추출기 | backend/knowledge/tacit_extractor.py | ✅ |
| 세션 프리로더 | backend/memory/preloader.py | ✅ |
| LLM 비용 로깅 (streaming_get → cost_log) | backend/main.py:1053 | ✅ |

### Frontend

| 컴포넌트 | 파일 | 상태 |
|---|---|---|
| 채팅 타임라인 (에이전트 버블 + PASS 행) | ChatTimeline.tsx | ✅ |
| 채팅 입력 (사일로 선택 + 파일 첨부) | ChatInput.tsx | ✅ |
| 에이전트 패널 (SVG 글리프 + ThinkingBars) | AgentPanel.tsx | ✅ |
| 헤더 (테마 토글 + WS 상태 뱃지) | Header.tsx | ✅ |
| 히스토리 사이드바 (세션 미리보기) | HistorySidebar.tsx | ✅ |
| 소스 사이드바 (ProbBar + 상세 패널) | SourceSidebar.tsx | ✅ |
| 지식 통계 (MiniSpark + 빈 DB 안내) | KnowledgeStats.tsx | ✅ |
| 케이스 서브헤더 (ID + 사일로 + Close) | ChatPage.tsx (inline) | ✅ |
| 리사이즈 레이아웃 | ResizableLayout.tsx | ✅ |
| 설정 페이지 (API키/모델/드롭다운/동기화) | SettingsPage.tsx + settings/ | ✅ |

---

## 디자인 시스템 (v2, 2026-04-27~)

- **디자인 토큰**: `--surface-*`, `--border-hairline/soft/medium`, `--agent-analyzer/finder/reviewer`, `--ct-*` (기여 타입별 edge/bg/fg)
- **다크 모드**: `[data-theme="dark"]` 전체 오버라이드
- **폰트**: Space Grotesk (sans) + JetBrains Mono — `var(--font-sans)` / `var(--font-mono)` 통일 완료
- **애니메이션**: dotBlink, shimmerLine, ringExpand, barGrow, streamCursor

---

## UX 기능 (2026-04-28 P0/P1/P2 완료)

| 항목 | 우선순위 | 상태 |
|---|---|---|
| EmptyState 씨드 쿼리 → ChatInput 자동 입력 | P1 | ✅ |
| CaseCompletion 배너 (케이스 종료 확인) | P1 | ✅ |
| CaseTitle 서브헤더 (ID + 사일로 + 기여 수) | P2 | ✅ |
| 세션 미리보기 텍스트 (SQL 서브쿼리) | P1 | ✅ |
| ChatInput P0 버그 수정 (사일로 없이 전송 가능) | P0 | ✅ |
| prefillText prop (씨드 버튼 → input 포커스) | P1 | ✅ |
| WS 재연결 테스트 픽스 (queueMicrotask flush) | 테스트 | ✅ |
| Layout.tsx 미사용 코드 제거 | 리팩토링 | ✅ |
| --font-family → --font-sans 통일 (7개 파일) | 리팩토링 | ✅ |

---

## 테스트 현황

### Frontend (vitest) — `cd frontend && npx vitest run`
```
Test Files  2 passed (2)
Tests       7 passed (7)
```

### Backend (pytest) — `source .venv/bin/activate && pytest tests/ -v`
- 35개 테스트 파일 존재
- venv 활성화 필요: `source .venv/bin/activate`
- 마지막 확인: 이전 세션 기준 전체 통과

---

## 미해결 / 외부 의존 항목

| 항목 | 이유 | 조치 방법 |
|---|---|---|
| DB Builder 실사용 검증 | PySide6 GUI 앱 — 직접 실행 필요 | `python dbbuilder/main.py` 실행 후 수동 검증 |
| 실제 API 키 E2E 테스트 | OpenRouter/OpenAI 키 필요 | `.env` 키 설정 후 실제 대화 테스트 |
| 프로덕션 배포 패키지 | 인프라 결정 필요 | Docker 또는 PyInstaller 빌드 논의 |

---

## 주요 설계 결정 기록

- **LLM 비용 로깅**: `streaming_get` 내부에서 에이전트 호출 후 `db.log_cost()` 호출 — 대시보드에 실시간 비용 반영
- **사일로 필터링**: `{account}_{tool}_{component}` 키로 ChromaDB 쿼리 범위 제한
- **StrictMode WS 보호**: `activeRef` + `queueMicrotask` 패턴으로 이중 마운트 시 고아 재연결 방지
- **세션 미리보기**: SQLite 상관 서브쿼리로 첫 번째 사용자 메시지 80자 추출

---

## 빠른 실행 명령

```bash
# 백엔드
source .venv/bin/activate
uvicorn backend.main:app --port 8000 --reload

# 프론트엔드
cd frontend && npm run dev       # http://localhost:3000 (또는 3001)

# 테스트
source .venv/bin/activate && pytest tests/ -v
cd frontend && npx vitest run

# 부트스트랩 (초기 데이터 투입)
python scripts/bootstrap.py --weekly data/raw/weekly_reports/example.xlsx

# Dreaming 파이프라인
python scripts/dreaming_cron.py
```
