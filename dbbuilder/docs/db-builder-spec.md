# ZEMAS DB Builder — 상세 기획서

**Project**: ZEMAS DB Builder (Knowledge Base Construction Pipeline)
**Parent**: ZEMAS Scaffolding Plan v3
**Author**: Kiwon (Application Engineer, ZEISS Korea)
**Date**: 2026-04-10
**Version**: 1.0

---

## 1. 개요

### 1.1 목적

ZEISS EUV 장비(PROVE, AIMS)의 매뉴얼, SOP, Weekly Report, Error Code DB 등
~1GB의 이질적 문서를 파싱→청킹→임베딩→ChromaDB에 적재하여
ZEMAS Finder agent가 검색할 수 있는 Knowledge Base를 구축한다.

### 1.2 앱 형태

- **Windows 무설치 standalone** (PyInstaller → 단일 .exe)
- **PySide6 (Qt6)** 네이티브 데스크톱 UI
- CLI 모드 지원 (`--cli` 플래그)

### 1.3 ZEMAS와의 관계

```
┌─────────────┐                     ┌──────────────────────┐
│  DB Builder  │──build-time────→   │  ChromaDB            │
│  (이 앱)     │   Type M chunks     │  data/chroma_db/     │
└─────────────┘                     │                      │
                                    │  ┌─ manuals ───────┐ │ ← DB Builder WRITE
                                    │  │ Type M chunks    │ │
                                    │  └─────────────────┘ │
                                    │  ┌─ case_records ──┐ │ ← ZEMAS WRITE
                                    │  │ Type A chunks    │ │
                                    │  └─────────────────┘ │
                                    │  ┌─ traces ────────┐ │ ← ZEMAS WRITE
                                    │  │ Type B chunks    │ │
                                    │  └─────────────────┘ │
                                    │  ┌─ weekly ────────┐ │ ← ZEMAS or DB Builder
┌─────────────┐                     │  │ Type C chunks    │ │
│   ZEMAS      │──runtime────→      │  └─────────────────┘ │
│  (본체 앱)   │   read + write      └──────────────────────┘
└─────────────┘
```

**규칙**:
- DB Builder는 `manuals` collection에만 WRITE
- `case_records`, `traces`는 절대 건드리지 않음
- `weekly`는 DB Builder가 bootstrap 시에만 WRITE (이후 ZEMAS가 운영 중 관리)

---

## 2. ZEMAS 연동 스키마

### 2.1 ChromaDB Collection 구조

ZEMAS는 4개의 ChromaDB collection을 사용한다. DB Builder는 이 중 `manuals`와 `weekly`에 적재한다.

| Collection | Chunk Type | 생성자 | ZEMAS 접근 | 설명 |
|------------|-----------|--------|-----------|------|
| `manuals` | Type M (manual) | DB Builder | read-only | 매뉴얼, SOP, Error DB 등 |
| `case_records` | Type A (case_record) | ZEMAS | read/write | LLM 요약된 케이스 |
| `traces` | Type B (conversation_trace) | ZEMAS | read/write | 원본 대화 (never_merge) |
| `weekly` | Type C (weekly_report) | DB Builder / ZEMAS | read/write | Weekly Report 행 |

### 2.2 공통 임베딩 모델

**모든 collection은 동일한 임베딩 모델을 사용해야 한다.**
검색 시 query embedding과 document embedding이 같은 벡터 공간에 있어야 유사도 계산이 유효하다.

```
모델: openai/text-embedding-3-small
차원: 1536
제공자: OpenRouter
비용: ~$0.02 / 1M tokens
설정 파일: data/config/models.json → roles.embedding
```

DB Builder는 ZEMAS의 `models.json`을 읽어서 임베딩 모델 설정을 가져온다.
하드코딩하지 않음 — models.json이 변경되면 DB Builder도 자동으로 따라감.

### 2.3 Silo Key 체계

ZEMAS Finder agent는 `silo_key`로 검색 범위를 필터링한다.

**형식**: `{account}_{tool}_{component}`

**유효한 값** (dropdowns.json 기준):

| Account | Tool | Components |
|---------|------|-----------|
| SEC | PROVE | InCell, Optics, Stage, SECS/GEM, Software |
| SEC | AIMS | Optics, Stage, Software, Detector |
| TSMC | PROVE | InCell, Optics, Stage, SECS/GEM, Software |
| TSMC | AIMS | Optics, Stage, Software, Detector |
| Intel | PROVE | InCell, Optics, Stage, SECS/GEM, Software |
| Intel | AIMS | Optics, Stage, Software, Detector |
| SKH | PROVE | InCell, Optics, Stage, SECS/GEM, Software |

**DB Builder에서의 silo_key 적용**:

- **매뉴얼 (Type M)**: `tool_family` 기반. 고객 무관하므로 silo_key 대신 `tool_family` 필터 사용.
  - 예: PROVE User Manual → `tool_family: "PROVE"` (silo_key 없음)
  - 예: AIMS EUV Guide → `tool_family: "AIMS"`
  - ZEMAS Finder가 매뉴얼 검색 시: `where={"tool_family": "PROVE"}`

- **Weekly Report (Type C)**: 고객+도구 기반 silo_key 부여.
  - 예: SEC / PROVE → `silo_key: "SEC_PROVE_InCell"` (component는 title에서 추론)

### 2.4 ZEMAS Finder 검색 흐름

Finder agent가 DB Builder의 결과를 어떻게 사용하는지 이해해야 한다:

```python
# Finder agent 검색 로직 (ZEMAS 쪽)
def search_knowledge(query: str, account: str, tool: str, component: str):
    # 1. Operational data 검색 (Type A/B/C)
    ops_results = vectordb.search_by_silo(
        collection_name="case_records",
        query=query,
        account=account, tool=tool, component=component,
        n_results=5
    )
    
    # 2. 매뉴얼 검색 (Type M) — DB Builder가 생성한 데이터
    manual_results = vectordb.search(
        collection_name="manuals",
        query=query,
        n_results=5,
        where={"tool_family": tool}  # ← tool_family 필터
    )
    
    # 3. Weekly Report 검색 (Type C)
    weekly_results = vectordb.search_by_silo(
        collection_name="weekly",
        query=query,
        account=account, tool=tool,
        n_results=5
    )
    
    # 4. 결과 합산 → context로 주입
    return merge_and_rank(ops_results, manual_results, weekly_results)
```

**결론**: DB Builder가 생성하는 chunk의 metadata 필드명과 값이 위 검색 로직과 정확히 일치해야 한다.

---

## 3. Chunk 메타데이터 스키마

### 3.1 Type M — 매뉴얼/SOP/Error DB Chunk

DB Builder가 `manuals` collection에 적재하는 chunk의 정확한 스키마:

```python
# ChromaDB upsert 시 전달하는 구조
{
    "id": str,              # 결정론적 ID (Section 3.3 참조)
    "document": str,        # chunk 텍스트 (markdown 형태)
    "embedding": list[float],  # 1536차원 벡터
    "metadata": {
        # === 필수 필드 (ZEMAS Finder 호환) ===
        "chunk_type": "manual",          # 고정값
        "source_file": str,              # "PROVE_UserManual_v3.pdf"
        "tool_family": str,              # "PROVE" | "AIMS" | "WLCD" | "FAVOR" | "general"
        
        # === 문서 구조 ===
        "page_number": int | None,       # 0-indexed PDF 페이지 번호
        "section_title": str,            # "Chapter 8 > 8.3 TIS Recalibration > Step 4"
        "section_path": str,             # JSON: ["Chapter 8", "8.3 TIS Recalibration", "Step 4"]
        "source_type": str,              # "manual" | "sop" | "error_db" | "cal_log" | "misc"
        
        # === 도메인 메타데이터 ===
        "customer": str,                 # "SEC" | "SKH" | "generic" (매뉴얼은 대부분 "generic")
        "document_version": str | None,  # "SW 5.6.2", "Rev.3"
        "language": str,                 # "en" | "de" | "ko" | "mixed"
        "is_safety_critical": bool,      # WARNING/CAUTION 블록 여부
        
        # === 품질 & 추적 ===
        "token_count": int,              # chunk의 토큰 수
        "quality_score": float,          # 0.0 ~ 1.0
        "ingested_at": str,              # ISO 8601
        
        # === 연결 (선택) ===
        "cross_references": str | None,  # JSON: ["Chapter 8.3", "Section 4.2"]
        "sheet_name": str | None,        # Excel 시트명 (해당 시)
        "issue_thread_id": str | None,   # Weekly Report용 (Type M에는 없음)
    }
}
```

### 3.2 Type C — Weekly Report Chunk

DB Builder가 `weekly` collection에 적재하는 chunk. ZEMAS `recording_policy.py`의 `build_type_c_chunk()`와 동일한 형식:

```python
{
    "id": "weekly-{cw}-{account}-{tool}-{title_hash8}",
    "document": "[{CW}] {account} {fob} {tool}\nTitle: {title}\nStatus: {status}\nNext Plan: {next_plan}",
    "embedding": list[float],
    "metadata": {
        "chunk_type": "weekly_report",   # 고정값
        "cw": str,                       # "CW15", "CW52"
        "account": str,                  # "SEC", "TSMC", "Intel", "SKH"
        "tool": str,                     # "PROVE", "AIMS"
        "component": str,               # title에서 추론 (없으면 빈 문자열)
        "fob": str,                      # Field of Business 코드
        "silo_key": str,                 # "{account}_{tool}_{component}" 또는 "{account}_{tool}"
        "title": str,                    # 이슈 제목
        "status": str,                   # "ongoing", "resolved", "open", "closed"
        "issue_thread_id": str,          # "thread-{sha256_hash[:12]}"
    }
}
```

**issue_thread_id 생성 규칙** (ZEMAS `recording_policy.py`와 동일):
```python
def generate_thread_id(account: str, tool: str, title: str) -> str:
    """같은 이슈를 여러 주차에 걸쳐 연결."""
    normalized = title.lower().strip()
    normalized = re.sub(r'v?\d+\.\d+(\.\d+)?', '', normalized)  # 버전 번호 제거
    normalized = re.sub(r'\s+', ' ', normalized)                  # 공백 정리
    key = f"{account}_{tool}_{normalized}"
    return f"thread-{hashlib.sha256(key.encode()).hexdigest()[:12]}"
```

### 3.3 Chunk ID 생성 규칙

**결정론적**: 같은 소스 파일을 다시 빌드하면 같은 ID가 나와야 함 (upsert 안전).

| Chunk Type | ID 형식 | 예시 |
|-----------|---------|------|
| Type M (매뉴얼) | `m-{file_hash6}_{page}_{index:03d}` | `m-a3f2b1_p042_002` |
| Type M (Excel) | `m-{file_hash6}_{sheet}_{index:03d}` | `m-b7c3d2_ErrorDB_015` |
| Type M (Word) | `m-{file_hash6}_{section}_{index:03d}` | `m-d4e5f6_s03_001` |
| Type C (Weekly) | `weekly-{cw}-{account}-{tool}-{title_hash8}` | `weekly-CW15-SEC-PROVE-a1b2c3d4` |

```python
def generate_chunk_id(source_file: str, location: str, chunk_index: int) -> str:
    """결정론적 chunk ID. 재빌드 시 동일 ID 보장."""
    file_hash = hashlib.md5(source_file.encode()).hexdigest()[:6]
    return f"m-{file_hash}_{location}_{chunk_index:03d}"
```

---

## 4. Parser 상세 명세

### 4.1 공통 인터페이스

모든 파서는 `BaseParser`를 구현하며, 동일한 출력 구조를 반환한다.

```python
@dataclass
class Table:
    """추출된 표."""
    headers: list[str]
    rows: list[list[str]]
    page_number: int | None = None
    caption: str | None = None

@dataclass
class ImageRef:
    """이미지 참조."""
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1
    caption: str | None = None
    ocr_text: str | None = None  # OCR 결과 (있으면)

@dataclass
class ParsedSection:
    """파서 출력 단위. 하나의 논리적 섹션."""
    text: str                          # markdown 형태의 본문
    section_path: list[str]            # ["Chapter 8", "8.3 TIS Recalibration"]
    page_range: tuple[int, int] | None # (시작 페이지, 끝 페이지), 0-indexed
    sheet_name: str | None             # Excel 시트명
    tables: list[Table]                # 포함된 표
    images: list[ImageRef]             # 포함된 이미지
    cross_refs: list[str]              # "See Chapter X.Y" 파싱 결과
    language: str                      # "en" | "de" | "ko" | "mixed"
    metadata: dict[str, Any]           # 파서별 추가 메타데이터

class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> list[ParsedSection]:
        """파일을 ParsedSection 리스트로 변환."""
        ...

    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """지원하는 파일 확장자 목록."""
        ...
```

### 4.2 PDF Parser

**라이브러리**: `pymupdf4llm` (1순위) + `pdfplumber` (표 추출 보강)

**처리 흐름**:
```
PDF 파일
  │
  ├─[1] pymupdf4llm.to_markdown() → 전체 문서 markdown 변환
  │     - 헤딩, 볼드, 리스트, 표 구조 보존
  │     - 이미지 위치 마커 포함
  │
  ├─[2] _detect_heading_hierarchy()
  │     - 폰트 크기/볼드 분석으로 Chapter > Section > Subsection 감지
  │     - TOC 페이지가 있으면 TOC 기반 구조 맵 생성
  │     - 결과: section_path 리스트
  │
  ├─[3] _extract_tables()
  │     - pymupdf의 표 추출이 불완전하면 pdfplumber로 재추출
  │     - 각 표를 Table 객체로 변환
  │     - 표 내용은 원본 텍스트에도 유지 (검색 가능성)
  │
  ├─[4] _parse_cross_references()
  │     - 정규식: "See (Chapter|Section|Table|Figure) [\d.]+"
  │     - 독일어: "Siehe (Kapitel|Abschnitt) [\d.]+"
  │     - 결과: cross_refs 리스트
  │
  ├─[5] _detect_safety_blocks()
  │     - "⚠ WARNING", "CAUTION", "DANGER", "WARNUNG", "VORSICHT"
  │     - 해당 블록 → is_safety_critical: true 메타데이터
  │     - 별도 chunk로 분리 (중요 안전 정보 독립 검색)
  │
  ├─[6] _detect_language()
  │     - langdetect 라이브러리로 페이지별 언어 감지
  │     - EN/DE 혼합 → "mixed"
  │     - 한국어 포함 시 → "ko" 또는 "mixed"
  │
  └─[7] _extract_version_markers()
        - "Valid from SW X.Y.Z", "Rev. N", "Version N.N"
        - document_version 메타데이터로 추출
```

**ZEISS 매뉴얼 특수 처리**:

| 특수 상황 | 처리 방법 |
|----------|----------|
| EN/DE 이중 언어 페이지 | 페이지별 language 태그. mixed인 경우 두 언어 모두 chunk에 포함 |
| 버전 마커 | "Valid from SW 5.6.2" → `document_version: "SW 5.6.2"` |
| WARNING/CAUTION 블록 | 별도 chunk + `is_safety_critical: true` |
| 목차 (TOC) | 파싱하여 section_path 생성에 활용. TOC 자체는 chunk로 만들지 않음 |
| 대형 표 (페이지 넘김) | pdfplumber로 multi-page 표 감지 → 하나의 Table로 병합 |
| 이미지 캡션 | 이미지 아래/위 텍스트를 caption으로 추출. ImageRef에 저장 |
| 빈 페이지 / 표지 | 의미 있는 텍스트 없으면 스킵 (quality gate에서 필터) |

### 4.3 Excel Parser

**라이브러리**: `openpyxl` (읽기) + `pandas` (데이터 처리)

**자동 모드 감지**:
```python
def _detect_mode(self, df: pd.DataFrame, sheet_name: str) -> str:
    columns = [str(c).strip().lower() for c in df.columns]
    
    # Weekly Report (new format): CW09 이후
    if any('cus' in c for c in columns) and any('fob' in c for c in columns):
        return "weekly_new"
    
    # Weekly Report (old format): CW52~CW08, Unnamed 컬럼
    if sheet_name.startswith("CW") and any('unnamed' in c for c in columns):
        return "weekly_old"
    
    # Error Code DB
    if any('error' in c and 'code' in c for c in columns):
        return "error_code_db"
    
    # Calibration Log
    if any('date' in c for c in columns) and any('parameter' in c for c in columns):
        return "calibration_log"
    
    # Generic Table
    return "generic_table"
```

**모드별 처리**:

#### Weekly Report (New Format)
```
시트명: CW15_New, CW14_New, ...
컬럼: Cus. | FoB | Tool | Title | Status | Next Plan

처리:
1. 각 행 = 1 ParsedSection
2. section_path = [시트명, 행 번호]
3. metadata에 cw, account(=Cus.), tool, fob, status 추출
4. issue_thread_id 자동 생성 (account + tool + normalized title)
```

#### Weekly Report (Old Format)
```
시트명: CW52, CW01, ...
컬럼: Unnamed:0 ~ Unnamed:N (헤더 없음 또는 병합 셀)

처리:
1. 첫 2~3행에서 실제 헤더 위치 감지 (빈 행 스킵)
2. 병합 셀 → 아래 행에 전파
3. 컬럼 매핑 추론: 위치 기반 (1열=Cus, 2열=FoB, 3열=Tool, ...)
4. 이후 new format과 동일하게 처리
```

#### Error Code DB
```
컬럼: Error Code | Description | Possible Cause | Resolution | Severity

처리:
1. 에러코드 1개 = 1 ParsedSection
2. 문서 텍스트: "[Error {code}] {description}\nCause: {cause}\nResolution: {resolution}"
3. metadata: source_type="error_db", tool_family 추론 (시트명 또는 코드 prefix에서)
```

#### Calibration Log
```
컬럼: Date | Parameter | Value | Unit | Operator | Notes

처리:
1. 날짜 기준 그룹핑 → session 단위 (같은 날 = 1 session)
2. session 1개 = 1 ParsedSection (여러 행 포함)
3. metadata: source_type="cal_log", source_date=session 날짜
```

#### Generic Table
```
처리:
1. 헤더 + 10~20행 = 1 ParsedSection (내용 길이에 따라 조정)
2. 각 chunk에 컬럼 헤더를 prefix로 포함
3. metadata: source_type="misc"
```

### 4.4 Word Parser

**라이브러리**: `python-docx`

**처리 흐름**:
```
DOCX 파일
  │
  ├─[1] 문서 열기 → paragraph + table 순회
  │
  ├─[2] 헤딩 기반 섹션 분할
  │     - Heading 1 → Chapter
  │     - Heading 2 → Section
  │     - Heading 3 → Subsection
  │     - 헤딩 없는 문서 → 전체를 1 섹션으로
  │
  ├─[3] 표 추출
  │     - docx.Table → Table 객체 변환
  │     - 표가 포함된 섹션에 tables 필드로 추가
  │
  ├─[4] Tracked Changes 보존 (선택)
  │     - revision 마크업 → metadata.tracked_changes에 저장
  │     - 변경 이력 자체가 암묵지 소스 (왜 절차가 바뀌었는지)
  │
  └─[5] 언어 감지 + 버전 마커 추출
        - PDF 파서와 동일한 로직
```

### 4.5 Image Parser

**라이브러리**: `pytesseract` (기본) / `paddleocr` (선택)

```
이미지 파일
  │
  ├─[1] 이미지 전처리
  │     - 그레이스케일 변환
  │     - 노이즈 제거 (bilateral filter)
  │     - 이진화 (Otsu's threshold)
  │
  ├─[2] OCR 실행
  │     - pytesseract.image_to_string(lang='eng+deu')
  │     - confidence score 추출
  │
  ├─[3] 구조 감지
  │     - 표 형태? → 격자 라인 감지 → Table로 구조화
  │     - 순수 텍스트? → 그대로 ParsedSection
  │     - 다이어그램? → 텍스트 부분만 추출, 나머지는 스킵
  │
  └─[4] 품질 경고
        - OCR confidence < 0.6 → quality_score에 반영
        - 텍스트 거의 없음 → 스킵 (quarantine)
```

### 4.6 Text Parser

```
텍스트 파일
  │
  ├─ .md → Markdown 헤딩(#, ##, ###) 기반 섹션 분할
  │        각 섹션 = 1 ParsedSection
  │
  ├─ .csv → pandas.read_csv() → Excel Generic Table 모드와 동일하게 처리
  │
  └─ .txt → 전체 텍스트 → sliding_window chunking으로 위임
```

### 4.7 파서 선택 매트릭스

파일 확장자 → 파서 자동 매핑:

| 확장자 | Parser | 비고 |
|--------|--------|------|
| `.pdf` | PDFParser | pymupdf4llm + pdfplumber |
| `.xlsx`, `.xls` | ExcelParser | 모드 자동 감지 |
| `.docx` | DocxParser | python-docx |
| `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp` | ImageParser | Tesseract OCR |
| `.md` | TextParser | 헤딩 기반 분할 |
| `.txt` | TextParser | sliding window |
| `.csv` | TextParser | pandas → generic table |
| 기타 | 스킵 | 로그에 경고 |

---

## 5. Chunking 전략

### 5.1 전략 매트릭스

| Source Type | Chunker | Token 범위 | 근거 |
|------------|---------|-----------|------|
| 매뉴얼 (절차서) | `HierarchicalChunker` | 512~1024 | Section 경계 보존, 절차 단위 일관성 |
| 매뉴얼 (이론/설명) | `SemanticChunker` | 1024~2048 | 긴 설명의 맥락 유지 |
| Weekly Report | `RowChunker` | 100~300 | 이슈 1건 = 1 chunk |
| Error Code DB | `RowChunker` | 150~400 | 코드 1개 = 1 chunk |
| Calibration Log | `RowChunker` | 200~500 | session 1개 = 1 chunk |
| SOP (Word) | `SemanticChunker` | 512~1024 | 절차 단계 경계에서 분할 |
| 스캔본 (이미지) | `SlidingWindowChunker` | 512 | OCR 출력은 구조 불확실 |
| 기타 텍스트 | `SlidingWindowChunker` | 512 | 구조 없는 텍스트 |

### 5.2 Hierarchical Chunker

매뉴얼의 Chapter > Section > Subsection 구조를 보존하는 핵심 chunker.

**원칙**:
1. **Breadcrumb 유지**: 모든 chunk에 상위 헤딩 경로 포함
2. **Section 경계 불가침**: Section 경계를 넘는 chunk 생성 금지
3. **짧은 섹션 병합**: `min_chunk_tokens` (50) 미만 → 인접 섹션과 병합
4. **긴 섹션 분할**: `max_chunk_tokens` (1024) 초과 → 내부에서 semantic boundary 분할

```python
def chunk(self, sections: list[ParsedSection]) -> list[Chunk]:
    for section in sections:
        breadcrumb = " > ".join(section.section_path)
        
        if token_count(section.text) <= max_tokens:
            # 섹션 전체가 하나의 chunk
            yield Chunk(
                text=f"[{breadcrumb}]\n{section.text}",
                section_path=section.section_path,
                page_range=section.page_range
            )
        else:
            # 섹션 내부 분할 (문장 경계에서)
            sub_chunks = split_at_sentence_boundaries(section.text, max_tokens)
            for i, sub_text in enumerate(sub_chunks):
                yield Chunk(
                    text=f"[{breadcrumb} (part {i+1}/{len(sub_chunks)})]\n{sub_text}",
                    section_path=section.section_path,
                    page_range=section.page_range,
                    part_index=i+1,
                    total_parts=len(sub_chunks)
                )
```

### 5.3 Row Chunker

Excel 행 단위 chunking. 헤더 컨텍스트를 모든 chunk에 포함.

```python
def chunk(self, rows: list[ParsedSection], header: str) -> list[Chunk]:
    for row in rows:
        yield Chunk(
            text=f"[{header}]\n{row.text}",
            section_path=row.section_path,
            sheet_name=row.sheet_name
        )
```

**Weekly Report 특수 처리**:
- 같은 Tool + Title (normalized) → `issue_thread_id` 부여
- Status가 "closed"/"resolved" → resolution 텍스트를 chunk에 포함

### 5.4 Semantic Chunker

문장 의미 경계에서 분할. SOP, 긴 설명 텍스트에 적합.

```python
def chunk(self, text: str, max_tokens: int) -> list[str]:
    sentences = split_sentences(text)
    current_chunk = []
    current_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if current_tokens + sentence_tokens > max_tokens and current_chunk:
            yield " ".join(current_chunk)
            # overlap: 마지막 2 문장을 다음 chunk에 포함
            current_chunk = current_chunk[-2:] if len(current_chunk) >= 2 else []
            current_tokens = sum(count_tokens(s) for s in current_chunk)
        current_chunk.append(sentence)
        current_tokens += sentence_tokens
    
    if current_chunk:
        yield " ".join(current_chunk)
```

### 5.5 Sliding Window Chunker

구조가 불확실한 텍스트의 fallback.

```
chunk_size: 512 tokens
overlap: 100 tokens
분할 단위: 문장 (가능하면) 또는 단어
```

---

## 6. Metadata Enrichment

### 6.1 자동 추출 규칙

| 필드 | 추출 방법 |
|------|----------|
| `tool_family` | 1) 파일명에서: "PROVE" → PROVE, "AIMS" → AIMS. 2) 파일명에 없으면 본문 키워드 빈도. 3) 판단 불가 → "general" |
| `customer` | 1) 파일 경로에 SEC/SKH/TSMC/Intel 포함 시. 2) Weekly Report의 Cus. 컬럼. 3) 매뉴얼은 대부분 "generic" |
| `language` | `langdetect` 라이브러리. 페이지/chunk 단위 감지. EN+DE 혼합 → "mixed" |
| `document_version` | 정규식: `(Valid from )?SW \d+\.\d+(\.\d+)?`, `Rev\.?\s*\d+`, `Version \d+` |
| `is_safety_critical` | 본문에 WARNING, CAUTION, DANGER, WARNUNG, VORSICHT, GEFAHR 포함 |
| `cross_references` | 정규식: `(See|Refer to|Siehe) (Chapter|Section|Table|Figure|Kapitel|Abschnitt) [\d.]+` |
| `section_title` | section_path의 마지막 요소 또는 breadcrumb 전체 |
| `source_date` | 파일 수정일, 또는 문서 내 날짜 파싱 |
| `token_count` | `tiktoken` (cl100k_base 인코더, OpenAI 모델과 동일) |

### 6.2 tool_family 감지 로직

```python
TOOL_KEYWORDS = {
    "PROVE": ["prove", "prove le", "prove-le", "proveⅱ"],
    "AIMS": ["aims", "aims euv", "aims-euv"],
    "WLCD": ["wlcd", "wafer level cd"],
    "FAVOR": ["favor", "defect inspection"],
}

def detect_tool_family(filename: str, text: str) -> str:
    # 1) 파일명 우선
    fn_lower = filename.lower()
    for tool, keywords in TOOL_KEYWORDS.items():
        if any(kw in fn_lower for kw in keywords):
            return tool
    
    # 2) 본문 키워드 빈도
    text_lower = text.lower()
    scores = {}
    for tool, keywords in TOOL_KEYWORDS.items():
        scores[tool] = sum(text_lower.count(kw) for kw in keywords)
    
    if max(scores.values()) > 5:  # 최소 5회 이상 언급
        return max(scores, key=scores.get)
    
    return "general"
```

### 6.3 Component 추론 (Weekly Report용)

```python
COMPONENT_KEYWORDS = {
    "InCell": ["incell", "in-cell", "aerial image", "focus"],
    "Optics": ["optics", "lens", "mirror", "illumination", "alignment"],
    "Stage": ["stage", "wafer stage", "reticle stage", "leveling"],
    "SECS/GEM": ["secs", "gem", "host", "communication", "recipe"],
    "Software": ["software", "sw", "ui", "gui", "update", "version"],
    "Detector": ["detector", "ccd", "camera", "sensor"],
}

def infer_component(title: str, tool: str) -> str:
    title_lower = title.lower()
    for comp, keywords in COMPONENT_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            # Detector는 AIMS에만 있음
            if comp == "Detector" and tool != "AIMS":
                continue
            return comp
    return ""  # 추론 불가 시 빈 문자열
```

---

## 7. Quality Gate

### 7.1 5가지 품질 메트릭

각 chunk에 5개 메트릭을 평가하고, 가중 평균으로 최종 quality_score를 산출한다.

| 메트릭 | 가중치 | 측정 대상 | 계산 방법 |
|--------|-------|----------|----------|
| `length` | 0.20 | 적절한 길이 | < 50 tokens → 0.0, 50~100 → 0.5, 100~2000 → 1.0, > 2000 → 0.7 |
| `coherence` | 0.30 | 문장 완성도 | 마지막 문장이 마침표/물음표/느낌표로 끝나면 1.0, 아니면 0.3. 중간에 잘린 단어 감지 → -0.3 |
| `noise` | 0.20 | 쓰레기 비율 | 공백/████/■/반복 특수문자 비율. < 5% → 1.0, 5~20% → 0.5, > 20% → 0.0 |
| `language` | 0.10 | 언어 일관성 | langdetect confidence. > 0.8 → 1.0, 0.5~0.8 → 0.7, < 0.5 → 0.3. mixed는 0.7 |
| `structure` | 0.20 | 메타데이터 완전성 | 필수 필드 존재 비율 (tool_family, section_title, source_file, language) |

```python
quality_score = (
    length * 0.20 +
    coherence * 0.30 +
    noise * 0.20 +
    language * 0.10 +
    structure * 0.20
)
```

### 7.2 Quarantine 정책

```
quality_score < 0.5 → status = "quarantined"
  → ChromaDB에 적재하지 않음
  → SQLite chunks 테이블에 quarantine_reason 기록
  → Inspector UI에서 수동 검토 가능:
    - [승인] → status = "accepted", ChromaDB에 적재
    - [수정] → 텍스트 편집 후 재평가, 통과 시 적재
    - [삭제] → status = "rejected", 영구 제외
```

---

## 8. Embedding Pipeline

### 8.1 처리 흐름

```
accepted chunks (SQLite)
  │
  ├─[1] 미임베딩 chunk 조회
  │     SELECT * FROM chunks WHERE status='accepted' AND is_embedded=0
  │
  ├─[2] BATCH_SIZE (100) 단위로 분할
  │
  ├─[3] OpenRouter API 호출
  │     POST https://openrouter.ai/api/v1/embeddings
  │     model: openai/text-embedding-3-small
  │     input: [chunk.text, chunk.text, ...] (최대 100개)
  │
  ├─[4] 응답 → embedding 벡터 (1536차원) 저장
  │     - SQLite: chunks.is_embedded = 1, chunks.embedded_at = now
  │     - ChromaDB: collection.upsert(id, embedding, document, metadata)
  │
  ├─[5] Checkpoint 저장 (매 100 batch)
  │     UPDATE checkpoints SET completed_chunks=N, last_batch_index=M
  │
  └─[6] 실패 처리
        - HTTP 429 (Rate Limit) → exponential backoff (2s, 4s, 8s)
        - HTTP 5xx → retry 3회 후 checkpoint_failures에 기록
        - 네트워크 에러 → checkpoint 저장 후 중단, 재시작 시 resume
```

### 8.2 Rate Limiting

```python
RATE_LIMIT_RPM = 3000          # OpenRouter default
BATCH_SIZE = 100               # chunks per API call
RETRY_MAX = 3
RETRY_BACKOFF_BASE = 2.0       # seconds

# 계산: 3000 RPM → 50 requests/sec
# 100 chunks/request → 5000 chunks/sec theoretical max
# 실제: API 응답 시간 고려하여 ~1000 chunks/sec
```

### 8.3 Checkpoint & Resume

```python
# 빌드 시작 시
checkpoint = {
    "job_id": uuid4(),
    "job_type": "full_build",
    "total_chunks": total,
    "completed_chunks": 0,
    "status": "running"
}

# 중단 후 재시작 시
pending = db.execute(
    "SELECT * FROM chunks WHERE status='accepted' AND is_embedded=0"
)
# → 이미 임베딩된 chunk는 자동으로 스킵됨
```

### 8.4 비용 추정

```
1GB 원본 → 파싱 후 ~500MB 텍스트 → ~2M tokens
text-embedding-3-small: $0.02 / 1M tokens
예상 비용: ~$0.04

text-embedding-3-large: $0.13 / 1M tokens
예상 비용: ~$0.26
```

---

## 9. ChromaDB Writer

### 9.1 Collection 설정

```python
client = chromadb.PersistentClient(path="data/chroma_db")

manuals_collection = client.get_or_create_collection(
    name="zemas_manuals",
    metadata={"hnsw:space": "cosine"}  # 코사인 유사도
)

# Weekly Report bootstrap 시에만
weekly_collection = client.get_or_create_collection(
    name="weekly",
    metadata={"hnsw:space": "cosine"}
)
```

### 9.2 Upsert 전략

```python
def upsert_batch(self, chunks: list[EmbeddedChunk]):
    """결정론적 ID로 upsert. 재빌드 시 자동 덮어쓰기."""
    self.collection.upsert(
        ids=[c.id for c in chunks],
        embeddings=[c.embedding for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[c.metadata_dict() for c in chunks]
    )
```

- **재빌드 안전**: 같은 파일 → 같은 chunk ID → upsert가 기존 데이터 덮어씀
- **증분 안전**: 새 파일 → 새 chunk ID → 기존 데이터에 영향 없음
- **삭제 시**: rebuild 명령 시에만 collection 전체 drop 후 재생성

### 9.3 Export

```python
def export(self, output_dir: Path):
    """ChromaDB persist directory를 ZEMAS 배포 위치로 복사."""
    shutil.copytree(
        self.persist_dir,
        output_dir,
        dirs_exist_ok=True
    )
```

---

## 10. SQLite 내부 스키마

DB Builder 내부 상태 관리용. ChromaDB와는 별개.

### 10.1 테이블 정의

```sql
-- 소스 파일 추적
CREATE TABLE files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path       TEXT NOT NULL UNIQUE,           -- raw_data_dir 기준 상대 경로
    file_hash       TEXT NOT NULL,                  -- SHA-256 (변경 감지용)
    file_size       INTEGER NOT NULL,               -- bytes
    source_type     TEXT NOT NULL,                  -- manual|weekly|sop|error_db|cal_log|image|misc
    detected_mode   TEXT,                           -- xlsx: weekly_new|weekly_old|error_code_db|cal_log|generic
    status          TEXT NOT NULL DEFAULT 'pending', -- pending|parsing|parsed|chunked|embedded|completed|failed
    error_message   TEXT,
    chunk_count     INTEGER DEFAULT 0,
    avg_quality     REAL,
    first_seen_at   TEXT NOT NULL,                  -- ISO 8601
    last_built_at   TEXT,
    updated_at      TEXT NOT NULL
);

-- 모든 chunk (accepted + quarantined)
CREATE TABLE chunks (
    id                  TEXT PRIMARY KEY,           -- 결정론적 ID
    file_id             INTEGER NOT NULL REFERENCES files(id),
    text                TEXT NOT NULL,
    token_count         INTEGER NOT NULL,
    
    -- ZEMAS 호환 메타데이터
    chunk_type          TEXT NOT NULL,              -- "manual" | "weekly_report"
    source_file         TEXT NOT NULL,
    source_type         TEXT NOT NULL,
    page_number         INTEGER,
    sheet_name          TEXT,
    tool_family         TEXT NOT NULL DEFAULT 'general',
    customer            TEXT NOT NULL DEFAULT 'generic',
    silo_key            TEXT NOT NULL DEFAULT '',
    section_path        TEXT,                       -- JSON array
    section_title       TEXT,
    document_version    TEXT,
    language            TEXT NOT NULL DEFAULT 'en',
    is_safety_critical  INTEGER NOT NULL DEFAULT 0,
    cross_references    TEXT,                       -- JSON array
    issue_thread_id     TEXT,
    source_date         TEXT,
    
    -- 품질
    quality_score       REAL,
    quality_detail      TEXT,                       -- JSON: {"length":0.8, ...}
    status              TEXT NOT NULL DEFAULT 'pending', -- pending|accepted|quarantined|rejected|edited
    quarantine_reason   TEXT,
    
    -- 임베딩 상태
    is_embedded         INTEGER NOT NULL DEFAULT 0,
    embedded_at         TEXT,
    
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- 임베딩 checkpoint
CREATE TABLE checkpoints (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              TEXT NOT NULL,
    job_type            TEXT NOT NULL,               -- full_build|incremental|single_file
    total_chunks        INTEGER NOT NULL,
    completed_chunks    INTEGER NOT NULL DEFAULT 0,
    last_batch_index    INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'running', -- running|paused|completed|failed
    started_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    completed_at        TEXT,
    error_message       TEXT
);

-- 실패한 chunk retry 목록
CREATE TABLE checkpoint_failures (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id       INTEGER NOT NULL REFERENCES checkpoints(id),
    chunk_id            TEXT NOT NULL,
    error_message       TEXT,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL
);

-- 빌드 이력
CREATE TABLE build_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              TEXT NOT NULL,
    total_files         INTEGER NOT NULL,
    total_chunks        INTEGER NOT NULL,
    accepted_chunks     INTEGER NOT NULL,
    quarantined_chunks  INTEGER NOT NULL,
    avg_quality         REAL NOT NULL,
    quality_distribution TEXT,                       -- JSON histogram
    source_type_breakdown TEXT,                      -- JSON: {"manual": 5000, ...}
    tool_family_breakdown TEXT,                      -- JSON: {"PROVE": 3000, ...}
    embedding_cost_usd  REAL,
    duration_seconds    REAL,
    created_at          TEXT NOT NULL
);

-- 인덱스
CREATE INDEX idx_chunks_file_id ON chunks(file_id);
CREATE INDEX idx_chunks_status ON chunks(status);
CREATE INDEX idx_chunks_quality ON chunks(quality_score);
CREATE INDEX idx_chunks_tool_family ON chunks(tool_family);
CREATE INDEX idx_chunks_is_embedded ON chunks(is_embedded);
CREATE INDEX idx_files_status ON files(status);
CREATE INDEX idx_checkpoints_job_id ON checkpoints(job_id);
```

---

## 11. 파이프라인 전체 흐름

```
사용자가 "Build" 버튼 클릭
    │
    ▼
[Pipeline Orchestrator]
    │
    ├─[1] Scan (FileScanner)
    │     - raw_data_dir 재귀 탐색
    │     - 확장자로 파서 매핑
    │     - SHA-256 해시 계산
    │     - files 테이블 insert/update
    │     - 이미 처리된 파일(해시 동일) 스킵
    │
    ├─[2] Parse (Parser)
    │     - 파일별 적절한 파서 호출
    │     - list[ParsedSection] 반환
    │     - files.status = "parsed"
    │
    ├─[3] Chunk (Chunker)
    │     - source_type에 따라 chunker 선택
    │     - list[Chunk] 반환
    │     - chunks 테이블에 insert
    │     - files.status = "chunked"
    │
    ├─[4] Enrich (MetadataExtractor)
    │     - tool_family, customer, language 등 자동 감지
    │     - section_title, cross_references 생성
    │     - silo_key 조합
    │     - chunks 테이블 update
    │
    ├─[5] Quality Gate (QualityMetrics)
    │     - 5 메트릭 평가 → quality_score
    │     - score >= 0.5 → status = "accepted"
    │     - score < 0.5 → status = "quarantined"
    │     - chunks 테이블 update
    │
    ├─[6] Embed (BatchEmbedder)
    │     - accepted chunks만 대상
    │     - batch 100개씩 OpenRouter API 호출
    │     - checkpoint 저장 (매 100 batch)
    │     - chunks.is_embedded = 1
    │     - files.status = "embedded"
    │
    └─[7] Write (ChromaDBWriter)
          - 임베딩된 chunk를 ChromaDB에 upsert
          - files.status = "completed"
          - build_reports 테이블에 요약 저장
```

---

## 12. 설정 (Config)

### 12.1 DBBuilderConfig

```python
@dataclass
class DBBuilderConfig:
    # === 경로 ===
    raw_data_dir: Path          # 소스 파일 디렉토리
    chromadb_dir: Path          # ChromaDB persist (ZEMAS와 공유)
    db_path: Path               # SQLite: db_builder.db
    zemas_config_dir: Path      # ZEMAS models.json 위치

    # === 임베딩 (models.json에서 읽음) ===
    embedding_model: str        # "openai/text-embedding-3-small"
    embedding_provider: str     # "openrouter"
    embedding_batch_size: int = 100
    embedding_dimension: int = 1536

    # === 청킹 ===
    max_chunk_tokens: int = 1024
    min_chunk_tokens: int = 50
    chunk_overlap_tokens: int = 100

    # === 품질 ===
    quality_threshold: float = 0.5

    # === 처리 ===
    max_concurrent_files: int = 4
    checkpoint_interval: int = 100   # batches per checkpoint
```

### 12.2 models.json 연동

DB Builder는 ZEMAS의 `data/config/models.json`을 읽기 전용으로 참조:

```python
def load_embedding_config(zemas_config_dir: Path) -> dict:
    models = json.loads((zemas_config_dir / "models.json").read_text())
    role_config = models["roles"]["embedding"]
    provider_config = models["providers"][role_config["provider"]]
    return {
        "model": role_config["model"],
        "provider": role_config["provider"],
        "base_url": provider_config["base_url"],
        "api_key_env": provider_config["env_key"],  # "OPENROUTER_API_KEY"
    }
```

### 12.3 환경 변수

```env
# .env (DB Builder 자체)
OPENROUTER_API_KEY=sk-or-...
ZEMAS_CONFIG_DIR=/path/to/ZZZ/data/config    # models.json 위치
ZEMAS_DATA_DIR=/path/to/ZZZ/data             # chroma_db 위치
```

---

## 13. 의존성

```toml
[project]
name = "zemas-db-builder"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # UI
    "PySide6>=6.7.0",
    
    # PDF
    "pymupdf4llm>=0.0.10",
    "PyMuPDF>=1.24.0",
    "pdfplumber>=0.11.0",
    
    # Excel
    "pandas>=2.2.0",
    "openpyxl>=3.1.0",
    
    # Word
    "python-docx>=1.1.0",
    
    # OCR (기본)
    "pytesseract>=0.3.10",
    
    # Embedding & VectorDB
    "httpx>=0.27.0",
    "chromadb>=0.5.0",
    "tiktoken>=0.7.0",
    
    # Data & Config
    "pydantic>=2.9.0",
    "python-dotenv>=1.0.0",
    
    # NLP
    "langdetect>=1.0.9",
]

[project.optional-dependencies]
ocr-paddle = ["paddleocr>=2.7.0", "paddlepaddle>=2.6.0"]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.24.0", "pyinstaller>=6.0.0"]
```

---

## 14. 구현 Phase 요약

| Phase | 범위 | 완료 기준 |
|-------|------|----------|
| **1** | Skeleton + Config + SQLite + BaseParser + FileScanner + UI Shell | pytest 통과, 빈 UI 표시 |
| **2** | 5개 파서 (PDF, Excel, Word, Image, Text) | 실제 파일 파싱 → ParsedSection 생성 확인 |
| **3** | 4개 Chunker + MetadataExtractor + QualityMetrics + Quarantine | chunk 생성 → 품질 평가 → quarantine 분류 |
| **4** | BatchEmbedder + ChromaDB Writer + Pipeline UI | E2E: 파일 10개 → ChromaDB 검색 성공 |
| **5** | Inspector/Quarantine/Stats UI + CLI + PyInstaller | Windows .exe 실행 → 전체 빌드 성공 |
