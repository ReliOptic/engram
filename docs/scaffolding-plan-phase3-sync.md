# Phase 3: Offline-First Sync — Mini PC 싱크 서버

> **원칙**: 과설계 금지. SQLite 파일 기반, 미니PC 하나, 로그인 없음.
> ZEMAS를 쓰면서 자연스럽게 지식이 쌓이고, 팀장이 되면 팀원 케이스가 자동으로 보이는 구조.

## 아키텍처

```
┌─ 미니PC (싱크서버) ─────────────────────┐
│  FastAPI (port 9000)                    │
│  SQLite: merged_zemas.db (모든 케이스)   │
│  ChromaDB: merged_chroma_db/ (모든 벡터) │
│  파일 서빙: manuals export 배포          │
└──────────┬──────────────────────────────┘
           │ HTTP (LAN / VPN)
     ┌─────┼─────┐
     │           │
 ┌───▼───┐  ┌───▼───┐
 │Kiwon  │  │AE-2   │
 │ZEMAS  │  │ZEMAS  │
 │local  │  │local  │
 └───────┘  └───────┘
```

## 동기화 모델: Push + Pull

### Push (클라이언트 → 서버)
케이스 닫을 때 자동 push:
- `POST /sync/cases` — Type A (case_record) chunk + metadata
- `POST /sync/traces` — Type B (conversation_trace) chunk
- `POST /sync/sessions` — session + messages (대화 기록)

### Pull (서버 → 클라이언트)
앱 시작 시 + 주기적 pull:
- `GET /sync/cases?since={timestamp}` — 다른 사람이 닫은 케이스
- `GET /sync/manuals?since={timestamp}` — DB Builder로 빌드한 매뉴얼
- `GET /sync/config` — models.json, dropdowns.json 최신 버전

### 충돌 전략
- **케이스**: 각 AE가 각자의 케이스를 품 → 충돌 안 남 (같은 케이스를 두 명이 동시에 안 함)
- **매뉴얼**: DB Builder에서 빌드 → 서버 push → 클라이언트 pull (단방향, 충돌 없음)
- **설정**: 서버가 master, 로컬은 override 가능

## 데이터 흐름

### 케이스 해결 시 (자동)
```
AE가 ZEMAS에서 대화 → 케이스 닫기
  → CaseRecorder: Type A + Type B chunk 생성
  → 로컬 ChromaDB + SQLite에 저장 (기존 동작)
  → SyncQueue에 push 이벤트 추가 (신규)
  → 온라인이면 즉시 서버로 push
  → 오프라인이면 큐에 저장, 다음 온라인 시 push
```

### 팀장 뷰 (자동)
```
Kiwon이 ZEMAS 열기
  → pull: 팀원들이 닫은 케이스 sync
  → 로컬 ChromaDB에 merge
  → 사이드바: 모든 팀원의 최근 케이스 표시
  → 검색: 팀 전체 지식베이스에서 검색
  → 보고서 불필요: 케이스 기록 = 업무 현황
```

### 매뉴얼 배포 (수동 트리거)
```
Kiwon이 DB Builder로 20GB 매뉴얼 빌드
  → ChromaDB manuals collection 완성
  → python -m db_builder --cli export --output /sync/manuals/
  → 서버에 올리기: scp 또는 HTTP upload
  → 팀원 ZEMAS: 다음 pull 시 자동 반영
```

## 구현 계획

### 3-A: SyncQueue (로컬 변경 추적)
**파일**: `backend/sync/queue.py`

```python
# SQLite에 sync_queue 테이블 추가
CREATE TABLE sync_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,  -- 'case_closed', 'session_created', 'message_added'
    collection TEXT NOT NULL,  -- 'case_records', 'traces', 'sessions'
    payload TEXT NOT NULL,     -- JSON: chunk data or session data
    created_at TEXT NOT NULL,
    synced_at TEXT,            -- NULL = not yet synced
    sync_server TEXT           -- which server received it
);
```

**변경점**:
- `backend/memory/case_recorder.py` — 케이스 닫을 때 sync_queue에 이벤트 추가
- `backend/main.py` — WebSocket 메시지 저장 시 sync_queue에 이벤트 추가

### 3-B: Sync Server (미니PC)
**새 프로젝트**: `sync_server/` (ZEMAS 프로젝트 안 또는 별도)

```
sync_server/
├── main.py          ← FastAPI app (port 9000)
├── database.py      ← SQLite: merged DB
├── config.py        ← 서버 설정 (.env)
├── install.bat      ← Windows 설치
└── run.bat          ← 실행
```

**엔드포인트**:
```
POST /sync/push          ← 클라이언트가 변경사항 push
GET  /sync/pull?since=   ← 클라이언트가 변경사항 pull
GET  /sync/manuals       ← 매뉴얼 ChromaDB snapshot download
POST /sync/manuals       ← DB Builder가 매뉴얼 upload
GET  /sync/status        ← 서버 상태 + 연결된 클라이언트 목록
GET  /sync/dashboard     ← 팀장 뷰: 모든 케이스 요약 (HTML)
```

**인증**: 없음. LAN 안에서만 접근. 나중에 필요하면 API key 하나 추가.

### 3-C: Sync Client (ZEMAS에 내장)
**파일**: `backend/sync/client.py`

```python
class SyncClient:
    def __init__(self, server_url: str | None):
        self.server_url = server_url  # None = 싱크 비활성
    
    async def push_pending(self):
        """sync_queue에서 미전송 이벤트를 서버로 push"""
    
    async def pull_updates(self, since: str):
        """서버에서 새 케이스/매뉴얼 pull → 로컬 DB에 merge"""
    
    def is_online(self) -> bool:
        """서버 연결 가능 여부"""
```

**변경점**:
- `backend/config.py` — `SYNC_SERVER_URL` 환경변수 추가 (없으면 싱크 비활성)
- `backend/main.py` — 앱 시작 시 `pull_updates()`, 케이스 닫을 때 `push_pending()`
- `.env.example` — `SYNC_SERVER_URL=http://192.168.1.100:9000` 추가

### 3-D: Frontend Sync UI
**변경점**:
- `Header.tsx` — 싱크 상태 아이콘 (🟢 synced / 🟡 pending / 🔴 offline)
- `HistorySidebar.tsx` — 케이스에 "by: Kiwon" 또는 "by: AE-2" 라벨
- `SettingsPage.tsx` — Sync 탭 추가 (서버 URL, 수동 push/pull 버튼, 큐 상태)

### 3-E: JSON Export (동료 공유용)
**파일**: `backend/sync/export.py`

```python
def export_knowledge(output_path: str, include: list[str]):
    """
    Export: cases + traces + weekly + manuals → ZIP
    동료에게 줄 때: python -m backend.sync.export --output zemas-knowledge.zip
    동료가 받을 때: python -m backend.sync.import --input zemas-knowledge.zip
    """
```

### 3-F: 팀장 대시보드
**서버 측 HTML 페이지**: `GET /sync/dashboard`

```
┌─ ZEMAS Team Dashboard ──────────────────────┐
│                                              │
│  이번 주 케이스                               │
│  ┌─────────┬──────┬────────┬───────────────┐ │
│  │ AE      │ Tool │ 건수   │ 최근 이슈      │ │
│  ├─────────┼──────┼────────┼───────────────┤ │
│  │ Kiwon   │PROVE │ 3      │ PRV-4412 TIS  │ │
│  │ AE-2    │AIMS  │ 2      │ AIMS detector │ │
│  │ AE-3    │PROVE │ 1      │ Stage level   │ │
│  └─────────┴──────┴────────┴───────────────┘ │
│                                              │
│  전체 지식베이스: 142 cases, 14 manuals       │
│  마지막 동기화: 2분 전                        │
└──────────────────────────────────────────────┘
```

## 환경 설정

### 미니PC 서버
```bash
# 설치
pip install fastapi uvicorn httpx chromadb python-dotenv

# .env
SYNC_PORT=9000
SYNC_DATA_DIR=./sync_data
SYNC_CHROMA_DIR=./sync_data/chroma_db

# 실행
uvicorn sync_server.main:app --host 0.0.0.0 --port 9000
```

### 클라이언트 (각 AE PC)
```bash
# .env에 추가
SYNC_SERVER_URL=http://192.168.1.100:9000
# 없으면 싱크 비활성 (기존 스탠드얼론 모드)
```

## 구현 순서 + 예상 시간

| # | 작업 | CC 예상 | 의존 |
|---|------|---------|------|
| 3-A | SyncQueue + event schema | ~30min | — |
| 3-B | Sync Server skeleton | ~1h | — |
| 3-C | Push/Pull client | ~1h | 3-A, 3-B |
| 3-D | Frontend sync UI | ~30min | 3-C |
| 3-E | JSON export/import CLI | ~30min | — |
| 3-F | Team dashboard (서버 HTML) | ~30min | 3-B |
| 3-G | Integration tests | ~30min | all |
| **Total** | | **~4.5h** | |

## 나중에 (팀 확장 시)
- API key 인증 추가 (1줄 미들웨어)
- user_id 필드 추가 (케이스에 "누가 풀었는지")
- Role 구분 (viewer vs editor)
- VPN 없이 접근 시 HTTPS + Let's Encrypt

## JSON 공유 플로우 (지금 당장 가능)

서버 없이도 동료에게 지식 전달:
```bash
# 내보내기 (Kiwon)
python -m backend.sync.export --output zemas-pack-20260412.zip

# 가져오기 (동료)
python -m backend.sync.import --input zemas-pack-20260412.zip
```

ZIP 내용: `cases.json` + `traces.json` + `chroma_db/manuals/` snapshot
