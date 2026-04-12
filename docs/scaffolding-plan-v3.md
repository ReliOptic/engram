# ZEISS EUV Multi-Agent Support System — Scaffolding Plan v3

**Project codename**: ZEMAS (ZEISS EUV Multi-Agent Support)
**Author**: Kiwon (Application Engineer, ZEISS Korea)
**Date**: 2026-04-10
**Status**: Planning → Ready for Claude Code scaffolding

---

## v3 changelog (from v2)

1. **Contribution 정의 구체화**: "기여 = 새 근거, 반론, user 질문, 이전 발언 수정" 중 하나. orchestrator가 파싱해서 검증.
2. **암묵지 추출 프롬프트**: 추상 개념 → LLM이 실행하는 구체 task로 변환. tacit_extractor 모듈 추가.
3. **Bootstrap 스크립트**: 초기 대량 데이터 인제스트 경로 (CW52~CW15 17개 시트 + 매뉴얼 PDF bulk).
4. **Spec-Driven + Test-Driven 개발 전략**: Claude Code 프롬프트 플로우 포함.

---

## 1~5: v2와 동일 (아래 delta만 반영)

### 3.1 delta — Contribution 정의 및 검증

**기여(Contribution)의 정의** — 다음 네 가지 중 하나에 해당해야 기여로 인정:

```python
CONTRIBUTION_TYPES = {
    "NEW_EVIDENCE":    "새로운 근거, 데이터, 소스를 제시",
    "COUNTER":         "다른 에이전트 의견에 반론 또는 수정 요청",
    "ASK_STAKEHOLDER": "user 또는 다른 에이전트에게 추가 정보 요청",
    "REVISE":          "자신의 이전 발언을 새 정보 기반으로 수정",
}
```

**Orchestrator 검증 로직**:

```python
def validate_contribution(response: AgentResponse) -> bool:
    """Agent 응답이 실질적 기여인지 검증."""
    # 1. 구조화된 output에서 contribution_type 필드 확인
    if response.contribution_type not in CONTRIBUTION_TYPES:
        return False
    
    # 2. "동의합니다" 수준의 rubber-stamp 감지
    if response.contribution_type == "NEW_EVIDENCE":
        # 실제로 새로운 정보가 포함되어 있는지 확인
        # (이전 대화에 없는 source_id, error_code, 절차 등)
        new_info = extract_new_info(response, conversation_history)
        if not new_info:
            return False  # "동의" 위장한 rubber-stamp
    
    return True
```

**Agent system prompt에 contribution 구조 강제**:

```
Every response MUST include:
1. contribution_type: one of [NEW_EVIDENCE, COUNTER, ASK_STAKEHOLDER, REVISE]
2. contribution_detail: what specifically you are adding
3. addressed_to: who this is for (@Analyzer, @Finder, @Reviewer, @You)
4. content: your actual message

If you have nothing substantive to add, respond with PASS.
Do NOT disguise agreement as contribution — "I agree with @Finder" is a PASS, not NEW_EVIDENCE.
```

### 5.1 delta — 암묵지 추출 프롬프트 (tacit_extractor)

"암묵지가 자연스럽게 드러난다"를 구체적 LLM task로 변환:

**Case close 시 실행되는 tacit extraction prompt**:

```python
TACIT_EXTRACTION_PROMPT = """
아래는 ZEISS EUV 장비 기술지원 에이전트와 AE/SE 사이의 대화 기록입니다.

이 대화에서 **매뉴얼이나 공식 문서에는 없지만, 현장 경험에서만 알 수 있는
판단, 절차, 맥락**을 추출해주세요.

추출 기준:
- 공식 절차에서 벗어난 현장 판단 (예: "시간 부족으로 TIS 스킵")
- 고객사별 특수 조건 (예: "SEC에서는 이 모드를 선호함")
- 에러 코드의 비공식 해석 (예: "PRV-4412는 보통 PM 후에 나오는데...")
- 장비 간 개체차이 (예: "m106은 stage drift가 좀 있음")
- 이전 경험 기반 우선순위 판단 (예: "이건 TIS부터 해봐야 돼")

추출하지 말 것:
- 매뉴얼에 명시된 표준 절차
- 인사말, 확인 요청 등 업무 외 대화
- 에이전트가 VectorDB/wiki에서 검색해온 정보 (이미 기록됨)

JSON 배열로 반환:
[
    {
        "signal": "SE가 PM 중 시간 압박으로 TIS recalibration을 스킵함",
        "type": "field_decision",       // field_decision | customer_specific | unofficial_interpretation | tool_specific | priority_judgment
        "source_speaker": "kiwon",
        "context": "post_PM, SEC PROVE LE#3",
        "confidence": 0.85,
        "related_procedure": "Ch.8.3 TIS recalibration"
    }
]

대화에서 암묵지가 발견되지 않으면 빈 배열 []을 반환하세요.

대화 기록:
{conversation_text}
"""
```

**tacit_extractor.py 모듈**:

```python
class TacitExtractor:
    """Case close 시 대화에서 암묵지 신호를 추출."""
    
    async def extract(self, conversation: list[Message]) -> list[TacitSignal]:
        conversation_text = format_conversation(conversation)
        response = await llm.call(
            model=AGENT_MODELS["dreaming"],  # 저렴한 모델 사용
            prompt=TACIT_EXTRACTION_PROMPT.format(conversation_text=conversation_text)
        )
        signals = parse_json_array(response)
        return [TacitSignal(**s) for s in signals if s]  # 빈 배열이면 빈 리스트
    
    def store(self, case_id: str, signals: list[TacitSignal]):
        """Type B chunk의 tacit_signals 필드에 저장."""
        vectordb.update(
            id=f"trace-{case_id}",
            metadata={"tacit_signals": [s.dict() for s in signals]}
        )
```

**Dreaming과의 연결**: Deep sleep에서 tacit_signals 필드만 스캔해서 반복 패턴 감지.
예: "TIS 스킵 → offset 발생"이 3건 이상 나타나면 graph 승격 후보.

### 5.5 (신규) — Bootstrap: 초기 대량 인제스트

```python
# scripts/bootstrap.py
"""
초기 설정 시 기존 데이터를 VectorDB에 bulk load.
사용법: python scripts/bootstrap.py --weekly data/raw/weekly_reports/CW15_Weekly_Apps.xlsx
        python scripts/bootstrap.py --manuals data/raw/manuals/
        python scripts/bootstrap.py --all
"""

def bootstrap_weekly(xlsx_path: str):
    """CW52~CW15 모든 시트를 파싱해서 Type C chunk로 적재."""
    xl = pd.ExcelFile(xlsx_path)
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name)
        # Format detection: CW09 이전 vs 이후 컬럼 구조가 다름
        if is_new_format(df):  # Cus. | FoB | Tool | Title | Status | Next Plan
            chunks = parse_new_format(df, sheet_name)
        else:  # Unnamed columns, merged cells
            chunks = parse_old_format(df, sheet_name)
        vectordb.upsert_batch(chunks)
    
    # Issue threading: 같은 이슈를 주별로 연결
    thread_weekly_issues()

def bootstrap_manuals(manuals_dir: str):
    """PDF 매뉴얼을 md로 변환 후 wiki에 적재."""
    for pdf in Path(manuals_dir).glob("*.pdf"):
        md = pdf_to_md(pdf)
        wiki.compile(md)
        vectordb.add_manual_chunks(md)

def bootstrap_all():
    bootstrap_weekly("data/raw/weekly_reports/CW15_Weekly_Apps.xlsx")
    bootstrap_manuals("data/raw/manuals/")
```

---

## 6~10: v2와 동일 (directory에 tacit_extractor.py, bootstrap.py 추가)

### 6 delta — 추가 파일

```
backend/knowledge/tacit_extractor.py   # 암묵지 추출 LLM task
scripts/bootstrap.py                    # 초기 bulk ingest
tests/                                  # TDD 테스트 디렉토리 (아래 상세)
├── conftest.py                         # Shared fixtures
├── test_orchestrator.py
├── test_contribution_validator.py
├── test_vectordb_recording.py
├── test_tacit_extractor.py
├── test_weekly_ingester.py
├── test_session_preloader.py
├── test_dedup.py
└── test_api_endpoints.py
```

---

## 11. Development strategy — Spec-Driven + Test-Driven

### 11.1 원칙

**Spec-Driven Development (SDD)**:
이 문서(scaffolding-plan-v3.md)가 single source of truth.
모든 구현은 spec의 데이터 구조, API 계약, 정책을 그대로 코드화.
spec에 없는 기능은 만들지 않음. spec과 코드가 괴리되면 spec을 먼저 업데이트.

**Test-Driven Development (TDD)**:
각 모듈마다 테스트를 먼저 작성하고, 테스트가 통과하는 최소 구현을 만듦.
테스트가 곧 spec의 실행 가능한 버전. "테스트에 없으면 구현하지 않는다."

**Integration test**: 각 Phase 완료 시 end-to-end 시나리오 테스트.
실제 PROVE/AIMS 케이스 시나리오로 전체 파이프라인 검증.

### 11.2 테스트 명세

**test_orchestrator.py**:
```python
def test_minimum_contribution_enforced():
    """모든 에이전트가 PASS 전에 최소 1회 기여해야 함."""

def test_rubber_stamp_rejected():
    """'동의합니다'만 말하면 기여로 인정 안 됨."""

def test_agent_can_mention_other_agent():
    """@Analyzer, @Finder 등 mention이 올바르게 라우팅됨."""

def test_ask_user_yields_turn():
    """ASK_STAKEHOLDER 시 user에게 턴이 넘어감."""

def test_max_rounds_terminates():
    """15라운드 초과 시 강제 종료 + 요약 생성."""

def test_all_pass_terminates():
    """모든 에이전트가 기여 후 PASS하면 종료."""
```

**test_contribution_validator.py**:
```python
def test_new_evidence_with_source():
    """새 source_id를 포함한 응답 → 기여 인정."""

def test_new_evidence_without_new_info():
    """이미 대화에 있는 정보 반복 → 기여 불인정."""

def test_counter_with_reasoning():
    """다른 에이전트 의견에 근거 있는 반론 → 기여 인정."""

def test_bare_agreement_rejected():
    """'동의합니다' → PASS로 재분류."""

def test_revise_changes_previous():
    """자신의 이전 발언을 수정 → 기여 인정."""
```

**test_vectordb_recording.py**:
```python
def test_case_close_creates_type_a():
    """케이스 종료 시 Type A (case_record) chunk 생성."""

def test_case_close_creates_type_b():
    """케이스 종료 시 Type B (conversation_trace) chunk 생성."""

def test_type_a_has_required_fields():
    """Type A chunk에 모든 필수 필드 존재."""

def test_silo_key_format():
    """silo key가 {account}_{tool}_{component} 형식."""

def test_weekly_creates_type_c():
    """xlsx 업로드 시 Type C (weekly_report) chunk 생성."""

def test_weekly_issue_threading():
    """같은 이슈가 여러 주에 걸치면 issue_thread_id 연결."""
```

**test_tacit_extractor.py**:
```python
def test_extracts_field_decision():
    """'시간 부족으로 TIS 스킵' → field_decision 타입 추출."""

def test_ignores_standard_procedure():
    """매뉴얼 표준 절차 → 추출하지 않음."""

def test_ignores_greetings():
    """인사말, 확인 요청 → 추출하지 않음."""

def test_empty_when_no_tacit():
    """암묵지 없는 대화 → 빈 배열 반환."""

def test_customer_specific_detected():
    """고객사별 특수 조건 → customer_specific 타입."""
```

**test_weekly_ingester.py**:
```python
def test_parse_new_format_cw15():
    """CW15 시트 (Cus.|FoB|Tool|Title|Status|Next Plan) 파싱."""

def test_parse_old_format_cw52():
    """CW52 시트 (Unnamed columns, merged cells) 파싱."""

def test_bootstrap_all_sheets():
    """CW52~CW15 17개 시트 전부 인제스트."""

def test_diff_detection():
    """CW14→CW15 변경사항 감지."""

def test_upsert_prevents_duplicate():
    """같은 CW+tool 조합은 upsert (덮어쓰기, 중복 아님)."""
```

**test_session_preloader.py**:
```python
def test_preloads_same_tool_cases():
    """같은 account+tool의 최근 10건 로딩."""

def test_preloads_cross_silo():
    """유사 이슈 cross-silo 5건 로딩."""

def test_preload_fits_context():
    """pre-loaded 컨텍스트가 256K 토큰 미만."""
```

**test_dedup.py**:
```python
def test_exact_duplicate_removed():
    """같은 case_id → 하나만 유지."""

def test_semantic_near_duplicate_merged():
    """cosine > 0.92 → LLM 머징."""

def test_conversation_trace_never_merged():
    """Type B chunk는 절대 머징하지 않음."""
```

### 11.3 Integration test 시나리오

```python
# tests/test_integration.py

def test_full_case_lifecycle():
    """
    실제 시나리오: PROVE InCell DB registration offset post-PM
    
    1. User submits: "PRV-4412, 3nm offset, RS3.0, post-PM"
    2. Analyzer: root cause candidates (TIS 78%, ref mark 15%)
    3. Finder: searches VectorDB, finds Case #0847, challenges Analyzer
    4. Analyzer: revises to TIS 65%, ref mark 25%
    5. Reviewer: asks user about SE report
    6. User: "SE confirmed TIS skipped"
    7. Analyzer: final → TIS only
    8. Reviewer: validates Ch.8.3 step 4-7
    9. Case close: Type A + Type B created
    10. Tacit extraction: "SE가 시간 압박으로 TIS 스킵" 추출
    11. Pre-load next session: this case appears in context
    """

def test_weekly_report_to_case_cross_reference():
    """
    시나리오: Weekly report 데이터가 case resolution에 활용됨
    
    1. Bootstrap: CW15 weekly report ingested
    2. User submits: "SEC LE#3 SECS/GEM 300 bug after SW upgrade"
    3. Finder: finds CW15 weekly entry about SW 5.6.2 upgrade
    4. Finder: cross-references CW12~CW14 thread showing issue history
    5. Reviewer: validates based on weekly report timeline
    """
```

---

## 12. Claude Code prompt flow — scaffolding to production

### 12.0 사전 준비

프로젝트 루트에 두 파일 배치:
- `scaffolding-plan-v3.md` (이 문서)
- `CW15_Weekly_Apps.xlsx` (실제 데이터)

### 12.1 CLAUDE.md 생성 프롬프트

```
이 프로젝트의 마스터 설계 문서는 scaffolding-plan-v3.md입니다.
CLAUDE.md를 생성해줘. 다음 내용을 포함:

1. 프로젝트 개요: ZEISS EUV Multi-Agent Support System (ZEMAS)
2. 핵심 원칙: spec-driven (이 문서가 truth), test-driven (테스트 먼저)
3. 개발 규칙:
   - scaffolding-plan-v3.md의 데이터 구조와 API 계약을 그대로 코드화
   - 모든 모듈은 테스트 먼저 작성 후 구현
   - TODO 주석 금지, 실제 동작하는 코드만
   - Python: pytest, async/await, type hints 필수
   - Frontend: React + TypeScript, Vite
4. 디렉토리 구조 참조: Section 6
5. 핵심 정책 참조: Contribution 정의(3.1), VectorDB Recording(5.1), Tacit Extraction(5.1 delta)
```

### 12.2 Phase 0-A: Backend 기반 (Day 1 오전)

```
scaffolding-plan-v3.md Section 6의 backend/ 디렉토리 구조를 만들어줘.

먼저 테스트부터:
1. tests/test_api_endpoints.py 작성 — FastAPI 서버 기동, health check, WebSocket echo
2. tests/conftest.py — 공통 fixtures (test client, mock LLM)

그 다음 구현:
1. backend/main.py — FastAPI app, CORS, WebSocket endpoint
2. backend/config.py — Section 2의 MODELS, AGENT_MODELS, BASE_URL 그대로
3. backend/utils/openrouter.py — multi-model OpenRouter client
4. data/config/dropdowns.json — Section 4의 Account>Tool>Component 계층 그대로
5. data/config/models.json — Section 2의 model registry 그대로

완료 기준: uvicorn main:app 으로 서버 기동, /health 200 OK, WebSocket echo 동작.
pytest tests/test_api_endpoints.py 전부 통과.
```

### 12.3 Phase 0-B: Orchestrator + Agents (Day 1 오후)

```
scaffolding-plan-v3.md Section 3.1의 orchestrator를 구현해줘.

먼저 테스트:
1. tests/test_orchestrator.py — v3 Section 11.2의 6개 테스트 케이스 그대로
2. tests/test_contribution_validator.py — v3 Section 11.2의 5개 테스트 케이스 그대로

그 다음 구현:
1. backend/agents/base_agent.py — OpenRouter LLM call, contribution_type 파싱
2. backend/agents/orchestrator.py — Section 3.1의 collaborative loop 코드 기반
   - CONTRIBUTION_TYPES 딕셔너리
   - validate_contribution() 함수
   - min-one-contribution 강제
   - @mention 라우팅
   - MAX_ROUNDS=15 초과 시 강제 종료
3. backend/agents/analyzer.py, finder.py, reviewer.py — Section 9의 system prompt 탑재

완료 기준: mock LLM으로 orchestrator 루프 동작.
에이전트 3명이 돌아가면서 발언, min-contribution 강제, rubber-stamp 거부.
pytest tests/test_orchestrator.py tests/test_contribution_validator.py 전부 통과.
```

### 12.4 Phase 0-C: Frontend shell (Day 1 저녁)

```
scaffolding-plan-v3.md Section 4의 3-column UI를 만들어줘.

React + Vite + TypeScript 프로젝트 생성.
1. frontend/src/components/Layout.tsx — 3-column grid (source | center | history)
2. frontend/src/components/AgentPanel.tsx — 3개 agent 카드, status 표시
3. frontend/src/components/ChatTimeline.tsx — 대화 메시지 렌더링, @mention 하이라이트
4. frontend/src/components/ChatInput.tsx — cascading dropdown (Account→Tool→Component) + 텍스트 입력 + 파일 업로드 버튼
5. frontend/src/components/SourceSidebar.tsx — 소스 문서 링크 리스트
6. frontend/src/components/HistorySidebar.tsx — 대화 요약 타임라인
7. frontend/src/hooks/useWebSocket.ts — backend WebSocket 연결

dropdowns.json에서 데이터를 로드해서 cascading dropdown 동작시켜줘.
mock 데이터로 에이전트 대화가 타임라인에 표시되도록.

완료 기준: npm run dev로 UI 표시, 3-column 레이아웃, dropdown cascading 동작.
```

### 12.5 Phase 1-A: VectorDB + Recording Policy (Day 2~3)

```
scaffolding-plan-v3.md Section 5.1의 VectorDB recording policy를 구현해줘.

먼저 테스트:
1. tests/test_vectordb_recording.py — v3 Section 11.2의 6개 테스트 케이스 그대로

그 다음 구현:
1. backend/knowledge/vectordb.py — ChromaDB wrapper
   - collection 생성/관리
   - silo key 기반 필터링: {account}_{tool}_{component}
   - similarity search + metadata filter 조합
2. backend/knowledge/recording_policy.py
   - build_type_a_chunk(): case close 시 LLM으로 구조화 요약 생성
   - build_type_b_chunk(): conversation trace 원문 저장
   - build_type_c_chunk(): weekly report 행 → chunk 변환
3. backend/memory/case_recorder.py — case close 시 Type A + Type B 자동 생성

CW15_Weekly_Apps.xlsx를 data/raw/weekly_reports/에 넣어뒀어.
실제 데이터로 Type C chunk 파싱 테스트도 해줘.

완료 기준: pytest tests/test_vectordb_recording.py 전부 통과.
ChromaDB에 실제 데이터가 저장되고 검색됨.
```

### 12.6 Phase 1-B: Tacit Extraction + Weekly Ingestion (Day 3~4)

```
scaffolding-plan-v3.md Section 5.1 delta의 tacit extractor를 구현해줘.

먼저 테스트:
1. tests/test_tacit_extractor.py — v3 Section 11.2의 5개 테스트 케이스 그대로
2. tests/test_weekly_ingester.py — v3 Section 11.2의 5개 테스트 케이스 그대로

그 다음 구현:
1. backend/knowledge/tacit_extractor.py
   - TACIT_EXTRACTION_PROMPT: Section 5.1 delta의 프롬프트 그대로
   - TacitExtractor.extract(): 대화 원문 → LLM → tacit_signals 리스트
   - TacitExtractor.store(): Type B chunk의 tacit_signals 필드에 저장
2. backend/knowledge/weekly_ingester.py
   - parse_new_format(): CW09+ 구조 파싱
   - parse_old_format(): CW52~CW08 구조 파싱 (Unnamed columns)
   - issue_thread_id 자동 생성 (같은 이슈 주별 연결)
3. scripts/bootstrap.py — Section 5.5의 bulk ingest
   - bootstrap_weekly(): 모든 CW 시트 순회
   - bootstrap_manuals(): PDF → md → VectorDB

CW15_Weekly_Apps.xlsx의 CW09_New 시트와 CW52 시트로
두 가지 포맷 파싱을 실제로 테스트해줘.

완료 기준: pytest tests/test_tacit_extractor.py tests/test_weekly_ingester.py 전부 통과.
python scripts/bootstrap.py --weekly로 17개 시트 전부 인제스트 성공.
```

### 12.7 Phase 1-C: Session Pre-loading + RAG (Day 4~5)

```
scaffolding-plan-v3.md Section 3.3의 session pre-loading을 구현해줘.

먼저 테스트:
1. tests/test_session_preloader.py — v3 Section 11.2의 3개 테스트 케이스 그대로

그 다음 구현:
1. backend/memory/preloader.py — Section 3.3의 build_session_context 코드 기반
2. backend/agents/finder.py 업데이트 — VectorDB search tool 연결
   - search_case_records(): Type A chunk 검색
   - search_weekly_reports(): Type C chunk 검색, issue_thread 포함
   - search_wiki(): wiki md 파일 검색

완료 기준: 새 세션 시작 시 관련 과거 케이스가 system prompt에 주입됨.
Finder가 실제로 VectorDB에서 관련 케이스를 찾아서 응답에 포함.
```

### 12.8 Phase 1-D: Frontend 완성 + Integration (Day 5~7)

```
frontend를 backend WebSocket에 연결하고, 전체 플로우를 통합해줘.

1. WebSocket 연결: 에이전트 메시지 실시간 수신 → ChatTimeline에 렌더링
2. Agent status: thinking/done/waiting 상태 실시간 업데이트
3. SourceSidebar: 에이전트가 참조한 source를 실시간으로 왼쪽에 추출
4. HistorySidebar: 대화 요약 + VectorDB에서 검색된 과거 케이스 표시
5. File upload: 파일 선택 → backend upload endpoint → 에이전트에게 전달
6. Settings page: dropdowns.json + models.json 편집 UI

integration test 실행:
tests/test_integration.py의 test_full_case_lifecycle 시나리오를
실제 OpenRouter API로 end-to-end 실행해줘.

완료 기준: 브라우저에서 문제 입력 → 에이전트 토론 → 솔루션 제시 → case close →
VectorDB에 저장 → 다음 세션에서 과거 케이스 참조 가능.
```

### 12.9 Phase 2: Dreaming (Week 3~6)

```
scaffolding-plan-v3.md Section 5.3의 Dreaming을 구현해줘.

먼저 테스트:
1. tests/test_dedup.py — v3 Section 11.2의 3개 테스트 케이스 그대로

구현:
1. backend/knowledge/dreaming.py — Light → REM → Deep 파이프라인
2. backend/knowledge/dedup.py — exact + semantic dedup + weekly threading
3. backend/knowledge/graph.py — NetworkX 기반 context graph
4. backend/knowledge/graph_export.py — Section 5.4의 export/import JSON
5. scripts/dreaming_cron.py — Windows Task Scheduler용 nightly job

완료 기준: 테스트 데이터로 dreaming 한 사이클 실행.
중복 entry 감지 → 머징. 패턴 감지 → graph 승격 후보 생성.
graph.json export → 다시 import → conflict detection 동작.
```

---

## 13. 핵심 프롬프트 규칙 (모든 Phase에 적용)

Claude Code에게 매 프롬프트마다 적용할 규칙:

1. **TODO 금지**: 모든 코드는 실제 동작해야 함. placeholder, stub, "implement later" 금지.
2. **테스트 먼저**: 구현 코드 전에 테스트 파일을 먼저 작성하고, 그 다음 구현.
3. **Spec 참조**: "scaffolding-plan-v3.md의 Section X를 구현"으로 정확한 위치 지정.
4. **완료 기준 명시**: 각 단계의 완료 기준을 만족하는지 확인 후 다음 단계로.
5. **실행 확인**: 서버 기동, pytest 실행, UI 렌더링을 실제로 확인.
6. **에러 시 즉시 수정**: 테스트 실패 시 다음 단계로 넘어가지 말고 즉시 수정.
7. **작은 단위**: 한 프롬프트에 한 모듈. 여러 모듈을 한 번에 시키지 않음.
