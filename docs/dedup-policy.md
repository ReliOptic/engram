# ZEMAS 데이터 중복 방지 정책 (Dedup Policy)

## 개요

동일한 Weekly Report 파일이나 케이스 데이터가 반복적으로 인제스트될 때의 처리 정책.

---

## 1. Weekly Report (Type C) — Deterministic ID 기반 Upsert

### 정책
- 각 weekly entry는 **deterministic chunk ID**를 가짐: `weekly-{CW}-{account}-{tool}-{sha256(title)[:8]}`
- 같은 CW + account + tool + title 조합 → **동일 ID** → `upsert`로 덮어쓰기 (최신 내용 유지)
- 새 CW 파일을 반복 실행해도 기존 데이터와 중복 생성되지 않음

### 예시
```
CW15 + SEC + LE#3 + "SW 5.6.2 SECS/GEM issue" → weekly-CW15-SEC-LE#3-a1b2c3d4
```
동일 파일 재인제스트 시: 같은 ID로 upsert → 내용만 갱신, 개수 불변

### Batch 내 중복
- 한 시트 안에 동일 issue가 여러 행으로 등장 시 → batch 내에서 마지막 행 유지
- `upsert_batch()` 내부에서 자동 deduplicate (같은 ID → 마지막 항목만)

---

## 2. Case Record (Type A) — Case ID 기반 Upsert

### 정책
- chunk ID: `case-{case_id}` (예: `case-SEC-2025-0200`)
- 같은 case를 다시 close하면 → upsert로 덮어씀
- Case 메타데이터는 SQLite에도 dual-write → `get_case()` 확인 후 없으면 create, 있으면 close만 갱신

### DB Builder와의 공존
- DB Builder가 manuals collection에 쓰는 chunk ID: `{filename}_{page}_{chunk_idx}`
- DB Builder 재실행 시 같은 PDF → 같은 ID → upsert로 안전하게 갱신
- ZEMAS의 case_records/traces와 DB Builder의 manuals는 **collection이 분리**되어 충돌 없음

---

## 3. Conversation Trace (Type B) — 절대 머징 금지

### 정책
- chunk ID: `trace-{case_id}`
- metadata에 `never_merge: True` 플래그
- Dreaming pipeline의 Light Sleep에서 traces collection은 **스캔만 하고 삭제/병합하지 않음**
- 이유: 대화 원문은 감사(audit) 및 tacit knowledge 추출의 원본 자료

---

## 4. Issue Threading — 같은 이슈의 주별 추적

### 정책
- issue_thread_id: `thread-{sha256(normalized_key)[:12]}`
- normalized_key: `{account}_{tool}_{title_normalized}`
- title 정규화: 소문자 변환 + 버전 번호 제거 + 공백 압축
- 같은 이슈가 CW14, CW15에 모두 나오면 → 서로 다른 chunk ID지만 **같은 thread_id**

### 예시
```
CW14: "SW 5.6.2 SECS/GEM 300 issue" → thread-abc123def456
CW15: "SW 5.6.2 SECS/GEM 300 issue" → thread-abc123def456 (동일!)
CW15: "SW 5.7.0 SECS/GEM 300 issue" → thread-abc123def456 (버전 번호 무시!)
```

---

## 5. Dreaming Pipeline 중복 제거

### Light Sleep (매일)
| Collection | 동작 | 비고 |
|-----------|------|------|
| case_records | Exact dedup (upsert 처리 완료) + near-duplicate 감지 (cosine > 0.92) | 감지만, 자동 삭제 안 함 |
| weekly | Exact dedup (upsert 처리 완료) + near-duplicate 감지 | 감지만 |
| traces | 스캔만 (never merge) | 절대 삭제/병합 안 함 |

### REM Sleep
- tacit_signals 메타데이터 스캔 → 3회 이상 동일 패턴 발견 시 promotion candidate 플래그

### Deep Sleep
- Knowledge Graph 재구축 → 기존 그래프와 merge (conflict detection)

---

## 6. 재인제스트 시나리오별 동작

| 시나리오 | 동작 | 데이터 손실 |
|---------|------|-----------|
| 같은 Weekly Excel 재실행 (`bootstrap.py --weekly`) | upsert → 내용 갱신, 개수 불변 | 없음 |
| 새 CW 시트가 추가된 Excel 실행 | 기존 CW는 upsert, 새 CW는 insert | 없음 |
| DB Builder로 같은 PDF 재처리 | manuals collection upsert → 갱신 | 없음 |
| Case 재close | case_records + traces upsert → 갱신 | 없음 |
| 완전히 다른 파일 인제스트 | 새 chunk ID → 추가 | 없음 |

---

## 7. 수동 정리가 필요한 경우

- Near-duplicate가 Light Sleep에서 감지되었을 때 → 관리자가 판단하여 수동 병합
- 잘못된 데이터가 인제스트된 경우 → chunk ID로 직접 삭제
- Collection 전체 초기화 → `data/chroma_db/` 디렉토리 삭제 후 재부트스트랩

```bash
# 전체 초기화
rm -rf data/chroma_db/
python scripts/bootstrap.py --weekly data/raw/weekly_reports/CW15_Weekly_Apps.xlsx

# Dreaming 리포트 확인
python scripts/dreaming_cron.py --export-graph data/graph.json
```
