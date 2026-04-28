# Engram 완성 가이드

> 현재 상태 · 남은 과제 · 프로덕션까지의 전 과정

작성일: 2026-04-29

---

## 1. 현재 상태 요약

### 완성된 것

| 영역 | 상태 | 비고 |
|------|------|------|
| 백엔드 API (FastAPI) | ✅ 완성 | 30+ 엔드포인트, WebSocket |
| 3-에이전트 시스템 | ✅ 완성 | Analyzer · Finder · Reviewer |
| 오케스트레이터 | ✅ 완성 | 병렬 실행, 반박 감지, 재시도 |
| VectorDB (ChromaDB) | ✅ 완성 | 4개 컬렉션, 사일로 필터링 |
| SQLite 구조화 DB | ✅ 완성 | 케이스 · 세션 · 비용 · 피드백 |
| 세션 관리 | ✅ 완성 | 생성·목록·히스토리·삭제·닫기 |
| 케이스 레코딩 | ✅ 완성 | Type A + Type B 청크 자동 생성 |
| 암묵지 추출 | ✅ 완성 | 케이스 종료 시 LLM 자동 추출 |
| 드리밍 파이프라인 | ✅ 완성 | Light/REM/Deep sleep 자동 실행 |
| 주간보고 자동 인제스트 | ✅ 완성 | xlsx 감지 → 자동 임베딩 |
| 임베딩 LRU 캐시 | ✅ 완성 | API 중복 호출 방지 |
| 동기화 시스템 | ✅ 완성 | SyncQueue · SyncClient · SyncServer |
| 프론트엔드 채팅 UI | ✅ 완성 | 타임라인 · 에이전트 패널 · 소스 사이드바 |
| 설정 UI | ✅ 완성 | 모델 · API키 · VectorDB · 드롭다운 · 비용 · 동기화 |
| DB Builder | ✅ 완성 | 문서 대량 임포트 GUI (PySide6) |
| CI/CD | ✅ 완성 | GitHub Actions — Windows/macOS 릴리즈 빌드 |
| 테스트 | ✅ 244개 통과 | pytest, vitest |

### 미완성인 것 (아래 섹션에서 상세 설명)

| 항목 | 우선순위 | 예상 작업량 |
|------|---------|-----------|
| LLM 비용 실제 연결 | P0 | 30분 |
| DB Builder 실사용 검증 | P0 | 1일 |
| 첫 실행 경험 (빈 DB 안내) | P1 | 2시간 |
| 프로덕션 배포 패키지 | P1 | 1일 |
| 실제 API 키로 엔드-투-엔드 테스트 | P0 | 반일 |

---

## 2. 완성 기준 (Definition of Done)

Engram이 "완성"되었다는 것은 다음 조건이 모두 충족될 때다.

```
□ 실제 API 키 (OpenRouter)로 3 에이전트가 기술 문제를 분석한다
□ 케이스 종료 시 VectorDB에 자동 저장되고, 다음 케이스에서 검색된다
□ DB Builder로 PDF/Word 매뉴얼을 임포트하면 Finder가 인용한다
□ 100번째 케이스는 1번째보다 빠르게 해결된다 (지식 누적 검증)
□ Windows · macOS에서 설치 없이 단독 실행 (PyInstaller 빌드)
□ LAN 내 2대 PC가 SyncServer를 통해 케이스를 공유한다
```

---

## 3. 남은 필수 과제

### P0 — 배포 전 반드시 해결

#### 3-1. LLM 비용 실제 연결

**문제:** `LLMClient.complete()`는 `estimated_cost_usd`를 계산하지만,
`streaming_get` (WebSocket 핸들러)이 이 값을 DB에 기록하지 않는다.
비용 대시보드가 항상 $0.00을 표시한다.

**수정 위치:** `backend/utils/llm_client.py` + `backend/main.py`

```python
# backend/utils/llm_client.py — complete() 끝에 추가
self.last_response: LLMResponse | None = None  # __init__에서 초기화

async def complete(self, role, messages, **kwargs) -> LLMResponse:
    ...
    self.last_response = response  # 마지막 호출 저장
    return response
```

```python
# backend/main.py — streaming_get 내부, response 반환 전 추가
if session_id and hasattr(llm, 'last_response') and llm.last_response:
    lr = llm.last_response
    try:
        app.state.db.log_cost(
            case_id=session_id,
            role=agent_name,
            model=lr.model,
            prompt_tokens=lr.prompt_tokens,
            completion_tokens=lr.completion_tokens,
            cost_usd=lr.estimated_cost_usd,
        )
    except Exception:
        pass
```

#### 3-2. 실제 환경 엔드-투-엔드 테스트

현재 테스트는 모두 `FakeEmbeddingFunction`과 mock LLM을 사용한다.
실제 API 키와 실제 데이터로 다음을 검증해야 한다.

```bash
# 1. OpenRouter API 키 설정 (Settings > API Keys)
# 2. 테스트 케이스 실행
# 3. 케이스 종료
# 4. 두 번째 케이스에서 첫 번째 케이스가 검색되는지 확인
```

**체크리스트:**
```
□ 에이전트 응답이 실제 JSON 형식으로 파싱됨
□ source_id 배지가 실제 청크를 가리킴
□ 케이스 종료 후 VectorDB에 Type A + B 청크 저장됨
□ 동일 문제 재발 시 Finder가 이전 케이스를 인용함
□ 비용이 Costs 탭에 기록됨
```

#### 3-3. DB Builder 실사용 검증

DB Builder가 생성한 `manuals` 컬렉션을 Engram이 올바르게 읽는지 확인.

```bash
cd dbbuilder
python -m db_builder --cli build --source /path/to/your/manuals/
# 생성된 chroma_db를 data/chroma_db에 복사
# Engram 재시작 후 Settings > VectorDB에서 manuals 청크 수 확인
# 케이스에서 Finder가 매뉴얼을 인용하는지 확인
```

**알려진 리스크:**
- DB Builder와 Engram의 임베딩 모델이 일치해야 함 (`openai/text-embedding-3-small`, 1536 dims)
- `test_integration_cross_project.py`가 이를 보장하지만 실제 문서로 검증 필요

---

### P1 — 실사용 품질

#### 3-4. 첫 실행 경험 개선

빈 DB에서 처음 실행하면 Finder가 "지식 베이스에 관련 케이스 없음"을 반환한다.
이것은 정상이지만 사용자가 당황할 수 있다.

**해야 할 것:**
- 빈 DB 첫 실행 시 온보딩 메시지 표시
- 매뉴얼 없이도 에이전트가 일반 지식으로 응답함을 안내
- 케이스 종료 후 "지식이 저장되었습니다" 알림

#### 3-5. 드롭다운 초기 데이터

`data/config/dropdowns.json`에 Account/Tool/Component 계층이 비어 있으면
사일로 선택을 할 수 없다.

```json
// data/config/dropdowns.json 예시
{
  "ClientA": {
    "ProductA": ["Module1", "Module2"],
    "ProductB": ["Module3"]
  }
}
```

**Settings > Dropdowns**에서 GUI로도 편집 가능하다.

#### 3-6. 에이전트 프롬프트 실사용 조정

현재 프롬프트는 일반적인 기술 지원을 위해 작성되어 있다.
실제 도메인 (예: 반도체 장비, 의료기기 등)에 맞게 조정하면 품질이 크게 향상된다.

```
data/config/agents/analyzer.md  — 증상 분석 전문화
data/config/agents/finder.md    — 검색 전략 전문화  
data/config/agents/reviewer.md  — 절차 검증 전문화
data/config/agents/common.md    — 공통 응답 형식 규칙
```

---

### P2 — 팀 사용 확장

#### 3-7. 팀 동기화 실사용

`sync_server/main.py`는 완성되어 있다. LAN 내 PC에서 실행하면 된다.

```bash
# 동기화 서버 (팀 공용 PC)
uvicorn sync_server.main:app --host 0.0.0.0 --port 9000

# 각 클라이언트 .env
SYNC_SERVER_URL=http://192.168.1.100:9000
SYNC_DEVICE_NAME=Engineer-PC-1
```

**검증 항목:**
```
□ PC-1에서 케이스 종료 → PC-2의 Settings > Sync > Pull Now에서 동기화됨
□ PC-2의 Finder가 PC-1의 케이스를 검색 결과로 반환함
□ 오프라인 상태에서 작업 → 온라인 복귀 후 자동 동기화됨
```

---

## 4. 데이터 투입 프로세스

지식 베이스를 채우는 3가지 경로:

### 경로 1: 케이스 해결 (자동 — 핵심 경로)

```
문제 입력 → 에이전트 분석 → 해결 → 케이스 종료
→ Type A (요약 청크) + Type B (대화 트레이스) 자동 저장
→ 다음 케이스부터 자동 검색됨
```

### 경로 2: 매뉴얼/SOP 임포트 (DB Builder)

```bash
cd dbbuilder

# GUI 방식
python -m db_builder

# CLI 방식
python -m db_builder --cli scan --source /매뉴얼/디렉토리
python -m db_builder --cli build
# 생성된 chroma_db를 engram/data/chroma_db에 복사/병합
```

**지원 형식:** PDF · Word (.docx) · Excel · Markdown · 텍스트

### 경로 3: 주간 보고서 자동 인제스트

```bash
# data/weekly_reports/ 디렉토리에 xlsx 파일 복사
cp 2024_CW15_report.xlsx data/weekly_reports/

# 서버가 실행 중이면 30초 내 자동 감지 및 인제스트
# 또는 수동 트리거:
curl -X POST http://localhost:8000/api/knowledge/ingest
```

---

## 5. 프로덕션 배포 프로세스

### 5-1. 단독 실행 파일 빌드 (현재 CI/CD)

GitHub Actions가 Windows/macOS용 단독 실행 파일을 자동 빌드한다.

```bash
# 로컬에서 빌드 (macOS)
.venv/bin/python build_mac.py  # PyInstaller spec 사용

# GitHub에 태그 푸시 시 자동 빌드
git tag v1.0.0
git push origin v1.0.0
# → GitHub Actions가 Windows + macOS 빌드 생성
```

빌드 결과물:
- `dist/engram/engram` (macOS)
- `dist/engram/engram.exe` (Windows)

### 5-2. 로컬 서버 방식 배포 (권장)

```bash
# 설치
git clone https://github.com/ReliOptic/engram.git
cd engram
python -m venv .venv
.venv/bin/pip install -e .

# 시작 스크립트 (start.sh)
#!/bin/bash
cd /opt/engram
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000

# macOS LaunchAgent로 자동 시작 설정
# Windows Task Scheduler로 자동 시작 설정
```

### 5-3. 환경 설정 체크리스트

```
□ Settings > API Keys에 OpenRouter API 키 입력
□ Settings > Dropdowns에 Account/Tool/Component 계층 설정
□ Settings > Models에서 사용할 LLM 모델 확인 (기본: gemini-2.0-flash-lite)
□ data/weekly_reports/ 디렉토리 생성
□ (팀 사용 시) .env에 SYNC_SERVER_URL 설정
```

### 5-4. Docker 배포 (선택)

현재 Dockerfile이 없다. 필요 시:

```dockerfile
# 추가 필요: Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e .
RUN cd frontend && npm install && npm run build
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 6. 운영 가이드

### 정기 점검 항목

| 주기 | 항목 | 방법 |
|------|------|------|
| 매일 밤 (자동) | 드리밍 파이프라인 | 자동 실행, Settings > VectorDB에서 확인 |
| 주 1회 | 주간보고 인제스트 | xlsx를 data/weekly_reports/에 복사 |
| 월 1회 | 비용 확인 | Settings > Costs |
| 월 1회 | 동기화 상태 확인 | Settings > Sync |
| 필요 시 | 수동 드리밍 실행 | Settings > VectorDB > 지금 실행 |

### 백업 방법

```bash
# VectorDB 백업
curl http://localhost:8000/api/settings/vectordb/export > backup_$(date +%Y%m%d).json

# SQLite 백업
cp data/sqlite/engram.db backups/engram_$(date +%Y%m%d).db
```

### 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 에이전트가 응답하지 않음 | API 키 미설정 | Settings > API Keys |
| Finder가 케이스를 못 찾음 | VectorDB 비어있음 | 케이스 축적 또는 DB Builder 사용 |
| 드리밍이 never_run | 최초 실행 전 | Settings > VectorDB > 지금 실행 |
| 동기화 상태 offline | 서버 미실행 | SYNC_SERVER_URL 확인 또는 standalone 모드 유지 |
| 비용이 $0.00 | cost 로깅 미연결 (P0 버그) | 섹션 3-1 수정 적용 |

---

## 7. 단계별 로드맵

### Phase 0 — 지금 당장 (1일)
```
□ LLM 비용 실제 연결 (섹션 3-1)
□ 실제 API 키로 엔드-투-엔드 1회 검증
□ dropdowns.json에 실제 장비 계층 입력
```

### Phase 1 — 첫 번째 실사용 팀 (1주)
```
□ DB Builder로 핵심 매뉴얼 10~20개 임포트
□ 실제 케이스 10개 해결 (지식 베이스 시딩)
□ 에이전트 프롬프트를 실제 도메인에 맞게 조정
□ 첫 실행 온보딩 메시지 추가
```

### Phase 2 — 팀 배포 (2주)
```
□ LAN 동기화 서버 세팅 및 검증
□ 2~3명이 동시에 사용하며 동기화 검증
□ 단독 실행 파일 배포 (GitHub Release)
□ Dockerfile 추가 (선택)
```

### Phase 3 — 지식 복리 확인 (1~3개월)
```
□ 50번째 케이스가 1번째보다 빠르게 해결되는지 측정
□ Finder 인용률 추적 (소스 배지 클릭 수)
□ 피드백 긍정률 추적 (Settings > Costs의 데이터 활용)
□ 드리밍 패턴 보고서 검토 (REM sleep 결과)
```

---

## 8. 코드베이스 현황 (숫자로)

```
백엔드 Python:      ~4,000줄 (tests 포함 ~7,500줄)
프론트엔드 TypeScript: ~3,500줄
테스트:             244개 통과 / 0개 실패
API 엔드포인트:     37개
에이전트 프롬프트:  4개 (analyzer, finder, reviewer, common)
빌드:               Windows + macOS CI/CD
번들 크기:          305 kB (프론트엔드)
```

---

## 9. 한 줄 요약

> 코드는 완성되었다. 지식이 비어 있을 뿐이다.  
> API 키를 연결하고, 매뉴얼을 임포트하고, 첫 케이스를 해결하면 시스템이 살아난다.
