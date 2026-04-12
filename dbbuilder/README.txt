================================================================
  Engram DB Builder v0.1.0
  Knowledge Base Construction Pipeline
  for Engram Multi-Agent Support System
================================================================

[Requirements]
  - Windows 10/11
  - Python 3.11 ~ 3.13 (python.org에서 설치)
    * 3.13t (free-threaded) 버전은 안 됨, 일반 버전 사용
  - 인터넷 연결 (OpenRouter API 호출용)


[최초 설치]

  1. install.bat 더블클릭
     → 가상환경(.venv) 생성 + 의존성 자동 설치
     → .env 파일 자동 생성

  2. .env 파일 열어서 OpenRouter API 키 입력
     OPENROUTER_API_KEY=sk-or-v1-...
     (키가 없으면 https://openrouter.ai 에서 발급)


[실행]

  GUI 모드:
    run.bat 더블클릭
    → 데스크톱 앱 실행 (Files / Build / Inspector / Statistics 탭)

  CLI 모드:
    run_cli.bat status    현재 상태 확인
    run_cli.bat scan      data\raw\ 폴더의 파일 스캔
    run_cli.bat build     빌드 파이프라인 실행 (Phase 2 이후)


[파일 넣는 법]

  data\raw\ 폴더 아래에 문서를 넣으면 됩니다:

    data\raw\manuals\       ← PDF 매���얼
    data\raw\weekly_reports\ ← Weekly Report Excel 파일
    data\raw\sops\           ← SOP Word 문서
    data\raw\images\         ← 스캔본, 사진 (PNG, JPG 등)
    data\raw\misc\           ← 기타 텍스트 (MD, TXT, CSV)

  지원 파일 형식:
    .pdf .xlsx .xls .docx .png .jpg .jpeg .tiff .bmp .md .txt .csv


[다른 PC로 이동]

  1. dbbuilder 폴더 전체를 복사
     (단, .venv 폴더는 빼도 됨 — 용량이 큼)

  2. 새 PC에서 install.bat 다시 실행
     → 가상환경 + 의존성 자동 재설치

  3. .env 파일에 API 키 다시 입력

  * Engram 본체 프로��트 없이도 독립 실행 가능
  * 처음 실행 시 config\models.json 자동 생성됨


[폴더 ���조]

  dbbuilder\
    install.bat          최초 설치 (1회)
    run.bat              GUI 실행
    run_cli.bat          CLI 실행
    .env                 API 키 설정
    .env.example         설정 예시
    src\                 ��스 코드
    tests\               테스트 코드
    docs\                기획서, 상태 문서
    data\                실행 시 자동 생성
      raw\               원본 문서 (여기에 파일 넣기)
      db_builder.db      SQLite 상태 DB
    config\              설정 (자동 생성)
      models.json        임베딩 모델 설정


[문제 해결]

  Q: install.bat에서 "Python not found" 에러
  A: python.org에서 Python 3.13 설치 후 재시도
     설치 시 "Add to PATH" 체크 필수

  Q: run.bat 실행 시 창이 안 뜸
  A: run_cli.bat status 로 먼저 동작 확인
     PySide6 설치 실패일 수 있음 → install.bat 재실행

  Q: API 호출 에러
  A: .env 파일의 OPENROUTER_API_KEY 확인
     https://openrouter.ai/settings/keys 에서 키 유효성 확인


================================================================
  Open Source — MIT License
================================================================
