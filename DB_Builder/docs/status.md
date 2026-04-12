# DB Builder — Status

**Last updated**: 2026-04-10

## Current Phase: Phase 2-4 Hybrid — IN PROGRESS

### Known Bug (Active)
**파일 업로드 후 리스트 미갱신**: Add Files/Folder로 파일 추가 시 파일은 복사되지만 테이블에 안 나타남.
- 원인 조사 중: ImportWorker(QThread) → finished(list) signal → _on_import_done → DB 등록 → _refresh_table 흐름에서 signal 전달 문제 의심
- 임시 해결: Refresh 버튼 클릭하면 표시됨
- CLI `python -m db_builder --cli scan` 으로도 등록 가능

---

## Completed

### Phase 1 (Skeleton) — COMPLETE
| 항목 | 파일 | 테스트 |
|------|------|--------|
| Config | `config.py` | 9 tests |
| SQLite DB | `database.py` | 32 tests |
| BaseParser | `parsers/base.py` | 38 tests |
| FileScanner | `pipeline.py` | 12 tests |
| PySide6 UI | `ui/main_window.py`, `app.py` | manual |
| CLI | `__main__.py` | manual |

### Embedding Pipeline — COMPLETE
| 항목 | 파일 | 테스트 |
|------|------|--------|
| Embedding Client | `embedding/client.py` | 10 tests |
| Batch Embedder | `embedding/embedder.py` | 13 tests |
| ChromaDB Writer | `store/chromadb_writer.py` | 16 tests |
| E2E Pipeline | `pipeline.py` (EmbeddingPipeline) | E2E API 통과 |

### Parsers + Chunking + LLM Enrichment — COMPLETE (code, not tests)
| 항목 | 파일 |
|------|------|
| File type detection | `filetype.py` — python-magic + magic bytes |
| Semantic chunking | `chunking/base.py` — SemanticChunker, MarkdownChunker |
| LLM Wiki enrichment | `enrichment.py` — chunk별 title/summary/keywords/cross-refs 생성 |
| Build pipeline | `ui/build_panel.py` — parse→chunk→enrich→embed→ChromaDB |

### GUI Features — COMPLETE
| 항목 | 파일 |
|------|------|
| Files tab | `ui/file_panel.py` — Add Folder/Files, 우클릭 메뉴, 알림 배너 |
| Build tab | `ui/build_panel.py` — Start/Pause/Resume/Stop 통합, 진행률 |
| Output tab | `ui/output_panel.py` — ChromaDB 상태, Export, 빌드 요약 |
| Settings | `ui/settings_dialog.py` — 경로, API 키, 임베딩 설정 |

**Total tests: 130/130 passing**

---

## 환경

- Python 3.12 (WSL) / 3.13 (Windows)
- venv: `.venv/`
- 설치: `install.bat` (Windows) or `uv pip install -e ".[dev]"` (WSL)
- 테스트: `python -m pytest tests/ -v`
- GUI: `run.bat` or `python -m db_builder`
- CLI: `run_cli.bat status` or `python -m db_builder --cli status`

## Windows Portable
- 위치: `C:\Users\ReliQbit\Downloads\ZEMAS_DB_Builder\`
- install.bat → run.bat 순서로 실행
- 다른 PC: .venv 빼고 복사 → install.bat 재실행

---

## Next Steps

1. **[BUG]** 파일 업로드 후 리스트 갱신 문제 해결
2. **Phase 2 테스트**: 파서별 단위 테스트 작성 (PDF, Excel, Word, Image)
3. **Phase 3 테스트**: chunking + quality metrics 단위 테스트
4. **Phase 5**: Inspector 탭 (chunk 브라우저), PyInstaller .exe 패키징

## 전체 Phase 로드맵

| Phase | 범위 | 상태 |
|-------|------|------|
| **1** | Skeleton + Config + SQLite + BaseParser + FileScanner + UI Shell | **COMPLETE** |
| **2** | Parsers (PDF, Excel, Word, Image, Text) | **COMPLETE** (code, tests pending) |
| **3** | Chunking + Metadata + Quality + LLM Enrichment | **COMPLETE** (code, tests pending) |
| **4** | Embedding + ChromaDB + Pipeline UI + E2E | **COMPLETE** |
| **5** | Inspector UI + PyInstaller .exe | PENDING |

## Key Decisions
- PySide6 (Qt) 네이티브 데스크톱 앱
- PyInstaller → Windows 무설치 단일 .exe (Phase 5)
- SQLite 단일 DB (상태 관리 전체)
- ZEMAS와 완전 독립 (models.json만 공유)
- Embedding: `openai/text-embedding-3-small` via OpenRouter
- LLM Enrichment: `google/gemini-2.0-flash-lite-001` via OpenRouter (무료)
- OCR: Tesseract 기본, PaddleOCR optional
- Wiki LLM 패턴: Karpathy 방식 — chunk별 LLM 요약/키워드/교차참조 생성
