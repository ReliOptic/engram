# ZEMAS DB Builder — Knowledge Base Construction Pipeline Spec

**Project codename**: ZEMAS DB Builder (ZEISS EUV Multi-Agent Support — Knowledge Base Builder)
**Parent project**: ZEMAS Scaffolding Plan v3
**Author**: Kiwon (Application Engineer, ZEISS Korea)
**Date**: 2026-04-10
**Status**: Spec Draft → Ready for implementation

---

## 0. Why a Separate App

ZEMAS의 `scripts/bootstrap.py`는 원래 초기 데이터 인제스트용으로 설계되었다.
그러나 실제 데이터 규모가 **~1GB, heterogeneous format (PDF + Excel + Word + images)**으로
확인된 시점에서, 이 작업을 ZEMAS 앱 내부에서 처리하는 것은 비현실적이다.

### 분리의 근거

| 문제 | ZEMAS 내장 시 | 독립 DB Builder 시 |
|------|-------------|------------------|
| 처리 시간 | 1GB PDF chunking+embedding = 수 시간. 개발 iteration 차단 | 비동기 배치, 야간 실행 가능 |
| 파이프라인 복잡도 | parser 디버깅이 orchestrator 개발을 방해 | 파서 품질을 독립적으로 반복 개선 |
| 반복 실험 | chunking 전략 변경 시 전체 앱 재시작 필요 | Inspector UI로 즉시 품질 확인 |
| 파일 타입 다양성 | PDF/Excel/Word/이미지 각각 다른 파서 필요 | 타입별 파서를 독립 모듈로 관리 |
| 품질 보증 | chunk 품질 확인 수단 없음 | Inspector UI + 자동 품질 메트릭 |

### ZEMAS와의 관계

```
[DB Builder] ──build──→ ChromaDB persist directory
                              │
                              ├── manuals collection (Type M) ← DB Builder가 생성
                              └── operational collection (Type A/B/C) ← ZEMAS가 운영 중 생성
                              │
[ZEMAS] ──read/write──→ ChromaDB
```

DB Builder는 **build-time tool**이다. ZEMAS 운영과 독립적으로 실행되며,
생성된 ChromaDB를 ZEMAS가 마운트해서 사용한다.

---

## 1. Scope — 무엇을 처리하는가

### 1.1 입력 소스 목록

| 소스 타입 | 예시 | 예상 규모 | 파서 |
|----------|------|----------|------|
| **매뉴얼 PDF** | PROVE User Manual, AIMS EUV Operation Guide, WLCD Handbook | ~500MB, 수천 페이지 | `pdf_parser` |
| **Excel 데이터** | Weekly Report (CW52~CW15), Calibration logs, Parts lists, Error code DB | ~100MB, 수십 시트 | `xlsx_parser` |
| **Word 문서** | SOP, 내부 기술 문서, Field Service Report | ~50MB | `docx_parser` |
| **이미지/스캔본** | 현장 사진, 스캔된 절차서, 다이어그램 | ~200MB | `image_parser` (OCR) |
| **기타 텍스트** | Markdown notes, txt logs, CSV exports | ~50MB | `text_parser` |

### 1.2 출력

- **ChromaDB persist directory**: ZEMAS Finder agent가 검색하는 벡터 DB
- **Metadata index**: 전체 인제스트 이력, 파일별 상태, chunk 통계
- **Quality report**: chunk 품질 메트릭 (평균 길이, 공백 비율, 언어 혼합도)

---

## 2. Architecture

### 2.1 Overall Pipeline

```
data/raw/                          tools/db-builder/
├── manuals/                       ├── pipeline.py          # 메인 오케스트레이터
│   ├── PROVE_UserManual_v3.pdf    ├── parsers/
│   ├── AIMS_EUV_OpGuide.pdf       │   ├── base.py          # Parser interface
│   └── ...                        │   ├── pdf_parser.py     # PDF → structured text
├── weekly_reports/                 │   ├── xlsx_parser.py    # Excel → row/table chunks
│   └── CW15_Weekly_Apps.xlsx      │   ├── docx_parser.py    # Word → structured text
├── sops/                          │   ├── image_parser.py   # OCR → text
│   └── PM_Procedure_SEC.docx      │   └── text_parser.py    # md/txt/csv passthrough
├── images/                        ├── chunking/
│   └── site_photos/               │   ├── semantic.py       # 긴 문서용 semantic chunking
└── misc/                          │   ├── row.py            # Excel 행 단위
                                   │   ├── hierarchical.py   # Chapter>Section>Subsection 보존
                                   │   └── sliding_window.py # fallback fixed-size
                                   ├── embedding/
                                   │   ├── embedder.py       # batch embedding engine
                                   │   └── models.py         # embedding model config
                                   ├── metadata/
                                   │   ├── extractor.py      # 파일/chunk 메타데이터 추출
                                   │   └── schema.py         # metadata field definitions
                                   ├── quality/
                                   │   ├── metrics.py        # chunk 품질 메트릭
                                   │   └── inspector.py      # Streamlit inspection UI
                                   ├── store/
                                   │   ├── chromadb_writer.py # ChromaDB에 적재
                                   │   └── export.py         # persist dir export
                                   ├── config.py             # 전역 설정
                                   └── cli.py                # CLI entry point
```

### 2.2 Pipeline Flow

```
파일 입력
    │
    ▼
[1. File Scanner] ── 확장자/MIME type으로 파서 선택
    │
    ▼
[2. Parser] ── 파일 타입별 텍스트+구조 추출
    │         ├── PDF: pymupdf4llm (markdown 변환) + 표/이미지 감지
    │         ├── Excel: openpyxl → 시트별 행/테이블 추출
    │         ├── Word: python-docx → 구조화 텍스트
    │         ├── Image: PaddleOCR/Tesseract → 텍스트
    │         └── Text: 직접 읽기
    │
    ▼
[3. Chunker] ── 문서 특성에 따라 chunking 전략 선택
    │         ├── 매뉴얼 → hierarchical (Chapter 구조 보존)
    │         ├── Excel → row-based (행 단위 + 헤더 컨텍스트)
    │         ├── SOP → semantic (절차 단위)
    │         └── 기타 → sliding window (fallback)
    │
    ▼
[4. Metadata Enricher] ── 각 chunk에 메타데이터 부착
    │         ├── source_file, page_number, section_path
    │         ├── document_type (manual | weekly | sop | error_db | ...)
    │         ├── tool_family (PROVE | AIMS | WLCD | FAVOR)
    │         ├── customer (SEC | SKH | generic)
    │         ├── language (en | de | ko | mixed)
    │         └── cross_references (parsed "See Chapter X.Y")
    │
    ▼
[5. Quality Gate] ── chunk 품질 검증
    │         ├── 최소 길이 체크 (< 50 tokens → 병합 또는 제거)
    │         ├── 공백/garbage 비율 체크
    │         ├── 언어 감지 일관성
    │         └── 품질 미달 → quarantine (격리) 큐
    │
    ▼
[6. Embedder] ── batch embedding
    │         ├── 모델: text-embedding-3-small (OpenAI) 또는 nomic-embed-text (로컬)
    │         ├── batch size: 100 chunks/call
    │         └── retry + rate limit handling
    │
    ▼
[7. ChromaDB Writer] ── collection에 적재
              ├── manuals collection: Type M chunks
              ├── silo key: {tool_family}_{document_type}
              └── persist directory로 export
```

---

## 3. Parser Specifications

### 3.1 PDF Parser (`pdf_parser.py`)

ZEISS 매뉴얼 PDF의 특수성을 처리하는 파서.

**라이브러리 선택**:
- **1순위**: `pymupdf4llm` — PDF를 LLM-friendly markdown으로 변환. 표, 이미지 위치, 헤딩 구조 보존.
- **2순위**: `pdfplumber` — 표 추출이 pymupdf보다 정확한 경우 fallback.
- **3순위**: RAG Anything (MinorU) — 복잡한 다이어그램/차트가 많은 문서에 한해 사용.

```python
class PDFParser(BaseParser):
    """ZEISS 매뉴얼 PDF를 구조화된 텍스트로 변환."""

    def parse(self, file_path: Path) -> list[ParsedSection]:
        """
        Returns:
            list of ParsedSection, each containing:
            - text: markdown 형태의 본문
            - section_path: ["Chapter 8", "8.3 TIS Recalibration", "Step 4"]
            - page_range: (start_page, end_page)
            - tables: list[Table] — 표가 있으면 별도 추출
            - images: list[ImageRef] — 이미지 위치 + caption
            - cross_refs: list[str] — "See Chapter X.Y" 파싱 결과
        """

    def _detect_heading_hierarchy(self, blocks) -> list[Heading]:
        """폰트 크기/볼드로 Chapter > Section > Subsection 감지."""

    def _extract_tables(self, page) -> list[Table]:
        """pdfplumber fallback으로 정확한 표 추출."""

    def _parse_cross_references(self, text: str) -> list[str]:
        """'See Chapter 8.3', 'Refer to Section 4.2' 등 파싱."""
```

**ZEISS 매뉴얼 특수 처리**:
- **이중 언어**: EN/DE 혼합 페이지 감지 → 언어 태그 부착
- **버전 마커**: "Valid from SW 5.6.2" 같은 버전 정보 → 메타데이터
- **경고/주의 블록**: ⚠️ WARNING, CAUTION 블록 → 별도 chunk + `is_safety_critical: true`
- **목차 → 구조 맵**: TOC 페이지를 파싱하여 전체 문서 구조 맵 생성

### 3.2 Excel Parser (`xlsx_parser.py`)

두 가지 모드: **Weekly Report 모드** (ZEMAS v3 bootstrap과 동일)와 **Generic Table 모드**.

```python
class ExcelParser(BaseParser):
    """Excel 파일을 chunk로 변환. 시트별로 모드 자동 감지."""

    def parse(self, file_path: Path) -> list[ParsedSection]:
        xl = pd.ExcelFile(file_path)
        results = []
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name)
            mode = self._detect_mode(df, sheet_name)

            if mode == "weekly_report":
                results.extend(self._parse_weekly(df, sheet_name))
            elif mode == "error_code_db":
                results.extend(self._parse_error_db(df, sheet_name))
            elif mode == "calibration_log":
                results.extend(self._parse_cal_log(df, sheet_name))
            else:
                results.extend(self._parse_generic_table(df, sheet_name))

        return results

    def _detect_mode(self, df, sheet_name) -> str:
        """컬럼 이름과 시트명으로 모드 추론.
        - 'Cus.' + 'FoB' + 'Tool' → weekly_report (new format)
        - 'Error Code' + 'Description' → error_code_db
        - 'Date' + 'Parameter' + 'Value' → calibration_log
        - else → generic_table
        """

    def _parse_weekly(self, df, sheet_name) -> list[ParsedSection]:
        """ZEMAS v3 Section 5.5의 new/old format 파싱 로직 그대로."""
        if self._is_new_format(df):
            return self._parse_new_format(df, sheet_name)
        else:
            return self._parse_old_format(df, sheet_name)
```

**행 단위 chunking 전략**:
- Weekly Report: 이슈 1건 = 1 chunk (Cus. + Tool + Title + Status + Next Plan)
- Error Code DB: 에러코드 1개 = 1 chunk (Code + Description + Possible Cause + Resolution)
- Calibration Log: 시간순 그룹핑 → session 단위 chunk
- Generic Table: 헤더 + N행 = 1 chunk (N = 10~20, 내용 길이에 따라 조정)

**컨텍스트 보존**: 모든 행 chunk에 시트 헤더를 prefix로 포함.
```
[Sheet: CW15_New | Columns: Cus. | FoB | Tool | Title | Status | Next Plan]
SEC | KR | PROVE LE#3 | DB registration offset post-PM | Open | TIS recal scheduled CW16
```

### 3.3 Word Parser (`docx_parser.py`)

```python
class DocxParser(BaseParser):
    """Word 문서를 구조화된 텍스트로 변환."""

    def parse(self, file_path: Path) -> list[ParsedSection]:
        """python-docx로 구조 추출. 헤딩 기반 섹션 분할."""

    def _extract_tracked_changes(self, doc) -> list[Change]:
        """Tracked changes → 메타데이터로 보존 (변경 이력이 암묵지 소스)."""
```

### 3.4 Image Parser (`image_parser.py`)

```python
class ImageParser(BaseParser):
    """스캔본/이미지에서 텍스트 추출."""

    def parse(self, file_path: Path) -> list[ParsedSection]:
        """
        1. PaddleOCR 또는 Tesseract로 텍스트 추출
        2. 구조 감지: 표 형태인지, 순수 텍스트인지, 다이어그램인지
        3. 다이어그램 → LLM description 생성 (선택적, 비용 주의)
        """
```

### 3.5 Text Parser (`text_parser.py`)

```python
class TextParser(BaseParser):
    """Markdown, txt, csv 등 텍스트 파일 직접 처리."""

    def parse(self, file_path: Path) -> list[ParsedSection]:
        """
        - .md → 헤딩 기반 섹션 분할
        - .csv → pandas로 읽어서 Excel parser의 generic table 모드 위임
        - .txt → sliding window chunking
        """
```

---

## 4. Chunking Strategy

### 4.1 전략 매트릭스

| 문서 타입 | Chunker | Chunk 크기 목표 | 이유 |
|----------|---------|---------------|------|
| 매뉴얼 (절차서) | `hierarchical` | 512~1024 tokens | Section 경계 보존, 절차 단위 일관성 |
| 매뉴얼 (이론/설명) | `semantic` | 1024~2048 tokens | 긴 설명의 맥락 유지 |
| Weekly Report | `row` | 100~300 tokens | 이슈 1건 = 1 chunk, 헤더 포함 |
| Error Code DB | `row` | 150~400 tokens | 코드 1개 = 1 chunk |
| SOP | `semantic` | 512~1024 tokens | 절차 단계 경계에서 분할 |
| 스캔본 | `sliding_window` | 512 tokens | OCR 출력은 구조가 불확실 |

### 4.2 Hierarchical Chunker (`hierarchical.py`)

ZEISS 매뉴얼의 Chapter > Section > Subsection 구조를 보존하는 chunker.

```python
class HierarchicalChunker:
    """문서 구조를 보존하면서 chunking.

    핵심 원칙:
    - 상위 헤딩은 항상 chunk에 포함 (breadcrumb)
    - Section 경계를 넘는 chunk 금지
    - 너무 짧은 subsection은 부모와 병합
    """

    def chunk(self, sections: list[ParsedSection]) -> list[Chunk]:
        chunks = []
        for section in sections:
            # breadcrumb 생성: "Chapter 8 > 8.3 TIS Recalibration > Step 4"
            breadcrumb = " > ".join(section.section_path)

            if section.token_count <= self.max_tokens:
                # 섹션 전체가 하나의 chunk
                chunks.append(Chunk(
                    text=f"[{breadcrumb}]\n{section.text}",
                    metadata=section.metadata
                ))
            else:
                # 섹션 내부를 semantic boundary에서 분할
                sub_chunks = self.semantic_split(section.text, self.max_tokens)
                for i, sub in enumerate(sub_chunks):
                    chunks.append(Chunk(
                        text=f"[{breadcrumb} (part {i+1}/{len(sub_chunks)})]\n{sub}",
                        metadata={**section.metadata, "part": i+1, "total_parts": len(sub_chunks)}
                    ))

        return chunks
```

### 4.3 Row Chunker (`row.py`)

```python
class RowChunker:
    """Excel 행 단위 chunking. 헤더를 컨텍스트로 포함."""

    def chunk(self, rows: list[ParsedSection], header: str) -> list[Chunk]:
        """각 행에 시트 헤더를 prefix로 부착.

        Weekly Report 특수 처리:
        - 같은 Tool + 같은 Title → issue_thread_id 부여
        - Status가 'Closed'면 resolution 포함
        """
```

---

## 5. Metadata Schema

### 5.1 공통 메타데이터 (모든 chunk)

```python
@dataclass
class ChunkMetadata:
    # === 소스 추적 ===
    source_file: str           # "PROVE_UserManual_v3.pdf"
    source_type: str           # "manual" | "weekly" | "sop" | "error_db" | "cal_log" | "image" | "misc"
    page_number: int | None    # PDF 페이지 (해당 시)
    sheet_name: str | None     # Excel 시트명 (해당 시)

    # === ZEISS 도메인 ===
    tool_family: str           # "PROVE" | "AIMS" | "WLCD" | "FAVOR" | "general"
    customer: str              # "SEC" | "SKH" | "generic"
    silo_key: str              # "{tool_family}_{source_type}" — ZEMAS 검색 필터용

    # === 문서 구조 ===
    section_path: list[str]    # ["Chapter 8", "8.3 TIS Recalibration"]
    document_version: str | None  # "SW 5.6.2", "Rev.3" 등
    language: str              # "en" | "de" | "ko" | "mixed"

    # === 품질 ===
    token_count: int
    quality_score: float       # 0.0 ~ 1.0
    is_safety_critical: bool   # WARNING/CAUTION 블록 여부

    # === 연결 ===
    cross_references: list[str]  # ["Chapter 8.3", "Section 4.2"]
    issue_thread_id: str | None  # Weekly Report 이슈 연결용

    # === 시간 ===
    ingested_at: str           # ISO 8601
    source_date: str | None    # 문서 작성일 (알 수 있으면)
```

### 5.2 ZEMAS 연동 — Silo Key 매핑

DB Builder의 `silo_key`는 ZEMAS Finder agent의 검색 필터와 일치해야 한다:

```python
# ZEMAS operational collection: {account}_{tool}_{component}
# DB Builder manuals collection: {tool_family}_{source_type}

# Finder 검색 시:
# 1. operational collection에서 silo_key = "SEC_PROVE_Stage" 로 검색 (Type A/B/C)
# 2. manuals collection에서 tool_family = "PROVE" 로 검색 (Type M)
# → 두 collection 결과를 합쳐서 context에 주입
```

---

## 6. Embedding Strategy

### 6.1 모델 선택

| 옵션 | 모델 | 차원 | 비용 | 용도 |
|------|------|------|------|------|
| **Cloud (기본)** | `text-embedding-3-small` (OpenAI) | 1536 | ~$0.02/1M tokens | 빠른 시작, 높은 품질 |
| **Cloud (고품질)** | `text-embedding-3-large` | 3072 | ~$0.13/1M tokens | 품질 최우선 시 |
| **Local** | `nomic-embed-text` (Ollama) | 768 | 무료 | 비용 절약, 민감 데이터 |

**권장**: `text-embedding-3-small`로 시작. 검색 품질 불만족 시 `large`로 전환.
1GB 원본 → 약 2M tokens 추정 → embedding 비용 ~$0.04 (small 기준). 무시할 수준.

### 6.2 Batch Processing

```python
class BatchEmbedder:
    """Rate limit 준수하면서 대량 embedding."""

    BATCH_SIZE = 100          # chunks per API call
    RATE_LIMIT_RPM = 3000     # OpenAI default
    RETRY_MAX = 3
    RETRY_BACKOFF = 2.0       # seconds, exponential

    async def embed_all(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """
        1. chunks를 BATCH_SIZE 단위로 분할
        2. rate limiter로 RPM 준수
        3. 실패 시 exponential backoff retry
        4. 진행률 표시 (tqdm)
        5. checkpoint: 100 batch마다 중간 결과 저장 → 중단 후 재시작 가능
        """

    async def _embed_batch(self, batch: list[Chunk]) -> list[list[float]]:
        """단일 batch embedding API 호출."""
```

### 6.3 Checkpoint & Resume

1GB 처리 중 네트워크 에러/API 장애로 중단될 수 있다.

```python
CHECKPOINT_FILE = "data/checkpoints/embedding_progress.json"

# checkpoint 구조:
{
    "total_chunks": 15000,
    "completed_chunks": 8400,
    "last_batch_index": 84,
    "failed_chunks": [1023, 5678],  # retry 대상
    "started_at": "2026-04-10T22:00:00",
    "elapsed_seconds": 3600
}
```

---

## 7. ChromaDB Collection Design

### 7.1 Collection 구조

```python
# DB Builder가 생성하는 collection
MANUALS_COLLECTION = "zemas_manuals"   # Type M chunks (매뉴얼, SOP, Error DB 등)

# ZEMAS가 운영 중 사용하는 collection (DB Builder는 건드리지 않음)
OPERATIONAL_COLLECTION = "zemas_operational"  # Type A/B/C chunks
```

**왜 2-collection인가**:
- `manuals`는 build-time에 한 번 생성, 이후 read-only. 변경 시 DB Builder로 재빌드.
- `operational`은 ZEMAS 운영 중 매 case마다 write. 빈번한 쓰기에 최적화.
- 분리하면 manuals 재빌드 시 operational 데이터에 영향 없음.

### 7.2 ChromaDB Writer

```python
class ChromaDBWriter:
    """Chunk를 ChromaDB에 적재."""

    def __init__(self, persist_dir: str = "data/chromadb"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=MANUALS_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )

    def upsert_batch(self, chunks: list[EmbeddedChunk]):
        """Batch upsert. ID 충돌 시 덮어쓰기 (재빌드 안전)."""
        self.collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=[c.embedding for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.metadata.dict() for c in chunks]
        )

    def export(self, output_dir: str):
        """persist directory를 ZEMAS 배포 위치로 복사."""
```

### 7.3 Chunk ID 전략

```python
def generate_chunk_id(source_file: str, page_or_sheet: str, chunk_index: int) -> str:
    """결정론적 ID → 재빌드 시 동일 chunk가 같은 ID를 받음.

    형식: {source_hash}_{location}_{index}
    예: "a3f2b1_ch8.3_002"
    """
    source_hash = hashlib.md5(source_file.encode()).hexdigest()[:6]
    return f"{source_hash}_{page_or_sheet}_{chunk_index:03d}"
```

---

## 8. Quality Assurance

### 8.1 자동 품질 메트릭 (`metrics.py`)

```python
class QualityMetrics:
    """각 chunk의 품질을 자동 평가."""

    def score(self, chunk: Chunk) -> float:
        """0.0 ~ 1.0 품질 점수. 아래 기준의 가중 평균."""

        scores = {
            "length": self._length_score(chunk),       # 50~2000 tokens 범위 내
            "coherence": self._coherence_score(chunk),  # 문장 완성도 (잘린 문장 감지)
            "noise": self._noise_score(chunk),          # 공백, 특수문자, garbage 비율
            "language": self._language_score(chunk),     # 언어 감지 일관성
            "structure": self._structure_score(chunk),   # 메타데이터 완전성
        }

        weights = {"length": 0.2, "coherence": 0.3, "noise": 0.2, "language": 0.1, "structure": 0.2}
        return sum(scores[k] * weights[k] for k in scores)

    def _length_score(self, chunk) -> float:
        """50 tokens 미만 → 0.0, 50~100 → 0.5, 100~2000 → 1.0, 2000+ → 0.7"""

    def _coherence_score(self, chunk) -> float:
        """마지막 문장이 완성형인지 (마침표/물음표로 끝나는지)."""

    def _noise_score(self, chunk) -> float:
        """공백, ████, ■, 반복 특수문자 비율."""
```

### 8.2 Quarantine Queue

```python
# quality_score < 0.5 → quarantine
# quarantine된 chunk는 ChromaDB에 넣지 않고 별도 파일에 저장
# Inspector UI에서 수동 검토 → 승인/수정/삭제
QUARANTINE_DIR = "data/quarantine/"
```

### 8.3 Inspector UI (`inspector.py`)

Streamlit 기반 품질 검사 도구.

```python
# streamlit run tools/db-builder/quality/inspector.py

"""
화면 구성:
┌──────────────────────────────────────────────────┐
│  [파일 필터] [품질 범위 슬라이더] [소스 타입 필터]    │
├──────────────────────────────────────────────────┤
│  파일별 통계                                       │
│  ├── PROVE_UserManual_v3.pdf: 342 chunks, avg 0.87 │
│  ├── CW15_Weekly_Apps.xlsx: 156 chunks, avg 0.92    │
│  └── ...                                            │
├──────────────────────────────────────────────────┤
│  Chunk 상세 뷰                                     │
│  ├── [텍스트 원문]                                  │
│  ├── [메타데이터 JSON]                              │
│  ├── [품질 점수 breakdown]                          │
│  └── [승인] [수정] [삭제] [quarantine 해제]          │
├──────────────────────────────────────────────────┤
│  Quarantine 큐 (품질 미달)                          │
│  ├── chunk_id: a3f2b1_p42_003, score: 0.31          │
│  └── ...                                            │
├──────────────────────────────────────────────────┤
│  전체 통계 대시보드                                  │
│  ├── 총 chunks: 15,234                              │
│  ├── 평균 품질: 0.84                                │
│  ├── Quarantine: 89 (0.6%)                          │
│  └── 소스별/타입별 분포 차트                          │
└──────────────────────────────────────────────────┘
"""
```

---

## 9. CLI Interface

### 9.1 Commands

```bash
# 전체 빌드 (모든 raw 데이터 → ChromaDB)
python -m tools.db_builder build --all

# 특정 소스 타입만
python -m tools.db_builder build --source manuals
python -m tools.db_builder build --source weekly
python -m tools.db_builder build --source sops

# 단일 파일
python -m tools.db_builder build --file data/raw/manuals/PROVE_UserManual_v3.pdf

# 품질 리포트
python -m tools.db_builder report

# Inspector UI 실행
python -m tools.db_builder inspect

# ChromaDB export (ZEMAS 배포용)
python -m tools.db_builder export --output /path/to/zemas/data/chromadb

# 상태 확인
python -m tools.db_builder status

# 재빌드 (기존 collection 삭제 후 재생성)
python -m tools.db_builder rebuild --all --confirm
```

### 9.2 Config (`config.py`)

```python
@dataclass
class DBBuilderConfig:
    # 경로
    raw_data_dir: str = "data/raw"
    chromadb_dir: str = "data/chromadb"
    checkpoint_dir: str = "data/checkpoints"
    quarantine_dir: str = "data/quarantine"

    # Embedding
    embedding_model: str = "text-embedding-3-small"    # or "nomic-embed-text"
    embedding_provider: str = "openai"                 # or "ollama"
    embedding_batch_size: int = 100
    embedding_dimension: int = 1536

    # Chunking defaults
    max_chunk_tokens: int = 1024
    min_chunk_tokens: int = 50
    chunk_overlap_tokens: int = 100

    # Quality
    quality_threshold: float = 0.5    # 미만 → quarantine

    # Processing
    max_concurrent_files: int = 4
    checkpoint_interval: int = 100    # batches
```

---

## 10. ZEMAS v3 Scaffolding Plan Delta

이 DB Builder 도입으로 scaffolding-plan-v3.md에 필요한 변경:

### 10.1 Section 5.5 (Bootstrap) 대체

기존 `scripts/bootstrap.py`의 `bootstrap_manuals()` 함수는 DB Builder로 대체.
`bootstrap_weekly()`는 DB Builder의 `xlsx_parser` weekly mode가 처리.

```python
# 기존 (v3):
# scripts/bootstrap.py → bootstrap_manuals() + bootstrap_weekly()

# 변경 (v3 + DB Builder):
# tools/db-builder/ → 모든 초기 인제스트 담당
# scripts/bootstrap.py → DB Builder 결과물을 ZEMAS에 연결하는 thin wrapper만 유지
```

### 10.2 Section 6 (Directory) 추가

```
tools/
└── db-builder/              # ← 신규
    ├── parsers/
    ├── chunking/
    ├── embedding/
    ├── metadata/
    ├── quality/
    ├── store/
    ├── config.py
    ├── pipeline.py
    └── cli.py
```

### 10.3 VectorDB 2-Collection 정책

```python
# backend/knowledge/vectordb.py 수정:

class VectorDB:
    def __init__(self):
        self.manuals = chromadb.PersistentClient("data/chromadb").get_collection("zemas_manuals")
        self.operational = chromadb.PersistentClient("data/chromadb").get_collection("zemas_operational")

    def search_manuals(self, query, tool_family=None, top_k=5):
        """Type M chunks 검색. DB Builder가 생성한 매뉴얼/SOP/Error DB."""
        where = {"tool_family": tool_family} if tool_family else None
        return self.manuals.query(query_texts=[query], n_results=top_k, where=where)

    def search_operational(self, query, silo_key=None, top_k=5):
        """Type A/B/C chunks 검색. ZEMAS 운영 중 생성된 케이스/weekly."""
        where = {"silo_key": silo_key} if silo_key else None
        return self.operational.query(query_texts=[query], n_results=top_k, where=where)
```

### 10.4 Phase 순서 조정

```
Phase 0-pre (신규): DB Builder 구축 + 초기 데이터 인제스트
    → 이 작업이 완료되어야 Phase 1-A (VectorDB + Recording)에서 검색 테스트 가능

Phase 0-A: Backend 기반 (변경 없음)
Phase 0-B: Orchestrator + Agents (변경 없음)
Phase 0-C: Frontend shell (변경 없음)
Phase 1-A: VectorDB → 2-collection 구조로 수정
Phase 1-B: Tacit Extraction + Weekly Ingestion → DB Builder의 weekly 결과 활용
    ...이하 동일
```

---

## 11. Development Strategy

### 11.1 구현 순서 (Claude Code prompt flow)

DB Builder는 ZEMAS와 독립적으로 개발하되, Phase 1-A 전에 완료해야 한다.

**Step 1: 뼈대 + PDF Parser**
```
tools/db-builder/ 디렉토리 구조를 만들어줘.

먼저 테스트:
1. tests/test_pdf_parser.py — 샘플 PDF로 heading 감지, 표 추출, cross-ref 파싱 테스트

그 다음 구현:
1. parsers/base.py — BaseParser interface (parse → list[ParsedSection])
2. parsers/pdf_parser.py — pymupdf4llm 기반. heading hierarchy, table extraction
3. config.py — 전역 설정
4. pipeline.py — 단일 파일 처리 flow (파서 선택 → 파싱)

완료 기준: 실제 ZEISS PDF 1개로 ParsedSection 리스트 생성 확인.
```

**Step 2: Excel Parser**
```
Weekly Report + generic table 파싱을 구현해줘.

먼저 테스트:
1. tests/test_xlsx_parser.py — CW15 new format + CW52 old format 파싱

구현:
1. parsers/xlsx_parser.py — 모드 자동 감지, weekly/error_db/cal_log/generic

완료 기준: CW15_Weekly_Apps.xlsx의 모든 시트 파싱 성공.
```

**Step 3: Chunking + Metadata**
```
chunking 전략과 metadata enrichment를 구현해줘.

먼저 테스트:
1. tests/test_chunking.py — hierarchical/row/semantic/sliding_window 각각
2. tests/test_metadata.py — 메타데이터 완전성 검증

구현:
1. chunking/hierarchical.py, row.py, semantic.py, sliding_window.py
2. metadata/extractor.py, schema.py

완료 기준: PDF → hierarchical chunks, Excel → row chunks, 메타데이터 완전.
```

**Step 4: Embedding + ChromaDB**
```
embedding pipeline과 ChromaDB 적재를 구현해줘.

먼저 테스트:
1. tests/test_embedder.py — batch embedding, checkpoint/resume
2. tests/test_chromadb_writer.py — upsert, 검색, ID 결정론성

구현:
1. embedding/embedder.py — batch + rate limit + checkpoint
2. store/chromadb_writer.py — 2-collection upsert + export

완료 기준: 실제 파일 10개로 end-to-end 파이프라인 실행.
ChromaDB에서 "PROVE TIS recalibration" 검색 시 관련 chunk 반환.
```

**Step 5: Quality + Inspector**
```
품질 메트릭과 Inspector UI를 구현해줘.

구현:
1. quality/metrics.py — 5개 메트릭 + 가중 평균
2. quality/inspector.py — Streamlit UI
3. cli.py — 전체 CLI

완료 기준: streamlit run으로 Inspector UI 동작.
quarantine chunk 목록 표시, 승인/삭제 동작.
python -m tools.db_builder build --all 로 전체 빌드 성공.
```

### 11.2 테스트 명세

```python
# tests/test_pdf_parser.py
def test_heading_hierarchy_detected():
    """Chapter > Section > Subsection 구조 감지."""

def test_table_extracted():
    """PDF 내 표가 별도 Table 객체로 추출."""

def test_cross_reference_parsed():
    """'See Chapter 8.3' → cross_references에 포함."""

def test_warning_block_flagged():
    """WARNING/CAUTION → is_safety_critical=True."""

def test_bilingual_detected():
    """EN/DE 혼합 페이지 → language='mixed'."""


# tests/test_xlsx_parser.py
def test_weekly_new_format():
    """CW15 new format 파싱 (Cus.|FoB|Tool|Title|Status|Next Plan)."""

def test_weekly_old_format():
    """CW52 old format 파싱 (Unnamed columns)."""

def test_mode_auto_detection():
    """시트 컬럼으로 weekly vs error_db vs generic 자동 감지."""

def test_issue_threading():
    """같은 Tool+Title → issue_thread_id 연결."""


# tests/test_chunking.py
def test_hierarchical_preserves_breadcrumb():
    """chunk에 section path breadcrumb 포함."""

def test_hierarchical_no_cross_section():
    """Section 경계를 넘는 chunk 없음."""

def test_row_includes_header():
    """행 chunk에 시트 헤더 prefix 포함."""

def test_min_length_merge():
    """50 tokens 미만 chunk는 인접 chunk와 병합."""


# tests/test_embedder.py
def test_batch_processing():
    """100 chunks씩 batch 처리."""

def test_checkpoint_resume():
    """중단 후 checkpoint에서 재시작."""

def test_rate_limit_respected():
    """RPM 한도 초과 시 대기."""


# tests/test_chromadb_writer.py
def test_upsert_idempotent():
    """같은 ID로 재적재 시 중복 없음."""

def test_search_by_tool_family():
    """tool_family='PROVE'로 필터링 검색."""

def test_deterministic_chunk_id():
    """같은 소스 → 같은 chunk ID."""


# tests/test_quality.py
def test_short_chunk_low_score():
    """10 tokens chunk → quality < 0.5."""

def test_garbage_detected():
    """████ 반복 → noise score 하락."""

def test_normal_chunk_passes():
    """정상 chunk → quality > 0.7."""
```

---

## 12. Risk & Mitigations

| 리스크 | 영향 | 완화 |
|-------|------|------|
| PDF 구조가 매뉴얼마다 제각각 | 파서가 heading 잘못 감지 | Inspector UI로 spot-check + 매뉴얼별 파서 config override |
| OCR 품질 낮음 (스캔본) | garbage chunk 대량 발생 | quality gate + quarantine + Tesseract↔PaddleOCR 비교 선택 |
| Embedding API 비용 초과 | 예산 문제 | 1GB → ~$0.04 (small). 문제없음. Large 쓰면 ~$0.26. 여전히 저렴 |
| ChromaDB 성능 (15K+ chunks) | 검색 느려짐 | metadata filter로 검색 범위 축소. 필요 시 collection 분리 추가 |
| 1GB 처리 중 중단 | 작업 손실 | checkpoint + resume 메커니즘 |
| ZEMAS와 collection 스키마 불일치 | Finder가 검색 실패 | silo_key 매핑 테스트를 integration test에 포함 |

---

## 13. Future Extensions (Phase 2+)

지금은 구현하지 않지만, 설계 시 고려:

1. **Incremental update**: 변경된 파일만 re-parse + re-embed (file hash 비교)
2. **LightRAG integration**: ChromaDB 대신 LightRAG의 knowledge graph로 전환
3. **Cross-reference graph**: "See Chapter X" 관계를 NetworkX graph로 구축 → ZEMAS Dreaming과 연결
4. **Multi-language search**: DE/EN/KO 쿼리가 모두 같은 chunk를 찾도록 cross-lingual embedding
5. **Version-aware retrieval**: SW 버전별 절차 차이를 반영한 검색 (version metadata 필터)
