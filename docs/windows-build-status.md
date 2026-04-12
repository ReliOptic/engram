# Windows CI Release Pipeline — 병목 분석

## 문제 정의

Windows CI release pipeline에서 DB Builder(PySide6) PyInstaller 단계가 과도하게 지연되어 전체 릴리즈가 멈춘다.

## 시도한 것

| # | 변경 | 결과 |
|---|------|------|
| 1 | PySide6 `--collect-all` 제거 → targeted imports | Engram 서버 ✅, DB Builder 여전히 느림 |
| 2 | chromadb `--collect-all` 제거 → targeted imports | 동일 |
| 3 | workflow + local bat 동시 반영 | 동일 |
| 4 | 태그 재생성 및 재빌드 (3회) | DB Builder 단계에서 매번 병목 |

## 확인된 사실

- macOS 전체 빌드 **성공** (Engram + DB Builder, ~7분)
- Windows Engram 서버 빌드 **성공** (CI)
- 로컬 Windows (WSL → cmd.exe) Engram + DB Builder **모두 성공**
- **Windows CI의 DB Builder packaging만 병목** — 40분+ 후에도 미완료

## 미확인 사항

- DB Builder CI 빌드가 실제로 **실패**하는지, 아니면 **매우 느린 것뿐**인지
- PyInstaller 분석 중 **어느 단계**(hook 수집, 바이너리 분석, 파일 복사)에서 멈추는지
- `--collect-all` 제거가 실제 속도에 얼마나 영향을 주었는지 (대조군 없음)

## 현재 가장 가능성 높은 원인

Windows GitHub runner에서 PyInstaller가 PySide6 관련 의존성을 수집하는 과정의 I/O 병목.

**근거:**
- macOS 성공 → 의존성 누락이 아닌 환경 문제
- 로컬 Windows 성공 → PyInstaller 설정 자체는 정상
- DB Builder에만 PySide6 포함 → PySide6가 병목 변수

**약화되는 가설:**
- "import 설정이 잘못됨" — macOS/로컬에서 동일 설정으로 성공
- "chromadb가 원인" — Engram 서버도 chromadb 사용하지만 성공

## 다음 단계 우선순위

### 1순위: DB Builder를 별도 job으로 분리
- 목적: **해결이 아니라 병목 위치를 격리**
- Engram 서버 릴리스는 DB Builder 없이도 진행 가능하게

### 2순위: 해당 step에 시간 로그/verbose 로그 삽입
- PyInstaller step 전후에 측정:
  - 시작/종료 시각
  - `dist/` `build/` 폴더 크기
  - `--log-level DEBUG` 로그
- "느림"이 아니라 **어느 수집 단계에서 멈추는지** 드러냄

### 3순위: 60분 timeout 명시
- 현재 GitHub Actions 기본 타임아웃은 6시간
- 명시적 60분으로 제한하여 빠른 실패 확인

### 4순위: 대안 검토
- PyInstaller 대신 **cx_Freeze** (PySide6 공식 권장, MSI 빌드 내장)
- DB Builder **배포 전략 분리** (`pip install engram-db-builder`)

## 소크라테스식 점검

1. **왜 "의존성 누락"이 아니라 "패키징 병목"인가?**
   macOS와 로컬 Windows에서 동일 설정으로 성공하므로, 코드/설정 문제가 아닌 환경 문제.

2. **macOS 성공과 로컬 Windows 성공은 어떤 가설을 지지/약화하는가?**
   지지: GitHub Actions Windows runner 특유의 I/O 병목.
   약화: PyInstaller 설정 오류, 의존성 누락.

3. **DB Builder만 별도 job으로 빼면 무엇이 명확해지는가?**
   Engram 서버 릴리스를 DB Builder에 독립시켜, 하나가 실패해도 나머지는 릴리스 가능.
   DB Builder의 정확한 소요 시간/실패 지점 격리.

4. **collect-all 제거가 충분조건이 아니라면, 다음 병목 후보는?**
   PyInstaller의 바이너리 분석 단계 (Qt DLL/plugins 스캔), GitHub runner 디스크 I/O.

5. **통합 installer여야 하는가, 컴포넌트 분리가 현실적인가?**
   사용자 관점에서 DB Builder는 선택적 도구. 분리 배포가 더 현실적일 수 있음.

## 파일 위치

| 파일 | 용도 |
|------|------|
| `.github/workflows/release.yml` | CI 워크플로우 |
| `scripts/build_windows.bat` | 로컬 빌드 (Engram + DB Builder) |
| `scripts/make_installer.bat` | 로컬 올인원 빌드 + Inno Setup |
| `scripts/engram-setup.iss` | Inno Setup 설치파일 스크립트 |
| `scripts/run_server.py` | Engram 서버 엔트리포인트 |

## 다음 대화용 프롬프트

> "아래 release workflow를 기준으로 DB Builder를 별도 Windows job으로 분리하고, PyInstaller step에 timing/verbose logging/timeout을 넣는 수정안을 작성해줘."
