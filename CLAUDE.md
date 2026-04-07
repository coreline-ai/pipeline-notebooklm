# CLAUDE.md

## Project Overview

**NotebookLM 자동화 파이프라인** - 외부 트리거로 URL/웹 요약본을 수신하여 NotebookLM AI 재요약 후 인포그래픽을 자동 생성, 저장, 전달하는 시스템.

```
트리거 수신 → URL/텍스트 입력 → NotebookLM 재요약 → 인포그래픽 생성 → 파일 저장 → 전달
```

## Architecture

### 핵심 전략: 독립 실행형 프로젝트

notebooklm-mcp-cli의 core/services/utils 소스를 프로젝트 내부에 vendor하여 **외부 패키지 없이 독립 실행**된다.

```
src/
├── notebooklm_tools/          ← vendored (notebooklm-mcp-cli 0.5.16 기반)
│   ├── core/                  ← API 클라이언트, 인증, HTTP 인프라
│   ├── services/              ← 비즈니스 로직 (sources, chat, studio, downloads)
│   └── utils/                 ← 설정, CDP, 브라우저 유틸
│
├── pipeline/                  ← 자체 구현 (자동화 레이어)
│   ├── core.py                ← 파이프라인 오케스트레이터
│   ├── poller.py              ← 아티팩트 완료 대기 (핵심 갭 해결)
│   ├── trigger.py             ← 트리거 수신
│   ├── delivery.py            ← 결과물 전달
│   └── config.py              ← 설정 관리
```

- `src/notebooklm_tools/`: notebooklm-mcp-cli에서 가져온 코드. cli/, mcp/ 제외.
- `src/pipeline/`: 이 프로젝트에서 자체 구현한 자동화 레이어.

## Development Commands

```bash
# 의존성 설치
uv sync

# 파이프라인 수동 실행
uv run python scripts/run_pipeline.py --url "https://..." --notebook-id "..."

# 테스트
uv run pytest

# notebooklm-mcp-cli 인증 (최초 1회, 이후 2~4주마다)
nlm login
nlm login --check
```

**Python requirement:** >=3.11

## Project Structure

```
project-01-notebooklm/
├── CLAUDE.md                     # 이 파일
├── AUTOMATION_MECHANISM.md       # 상세 설계 문서
├── pyproject.toml                # 프로젝트 설정 + 의존성
├── src/
│   ├── notebooklm_tools/         # vendored (notebooklm-mcp-cli 0.5.16)
│   │   ├── core/                 # API 클라이언트, 인증
│   │   ├── services/             # 비즈니스 로직
│   │   └── utils/                # 유틸리티
│   └── pipeline/
│       ├── __init__.py           # 패키지 초기화
│       ├── core.py               # 파이프라인 오케스트레이터 (메인 로직)
│       ├── poller.py             # 아티팩트 완료 폴링 (studio_status 기반)
│       ├── trigger.py            # 트리거 메커니즘 (webhook/cron/file)
│       ├── delivery.py           # 전달 메커니즘 (slack/email/file)
│       └── config.py             # 설정 로드 및 검증
├── configs/
│   └── default.yaml              # 기본 파이프라인 설정
├── scripts/
│   └── run_pipeline.py           # CLI 진입점
├── output/                       # 생성된 파일 저장 (gitignored)
└── tests/
    ├── test_core.py
    ├── test_poller.py
    └── conftest.py
```

## Key Design Decisions

### notebooklm-mcp-cli의 studio_create는 비동기 반환

`studio.create_artifact()`는 항상 `status: "in_progress"`를 반환한다.
인포그래픽 생성은 Google 서버에서 1~5분 소요된다.
따라서 **반드시 `poller.py`의 폴링 루프로 완료를 확인한 후** 다운로드해야 한다.
완료 전에 `download_async()`를 호출하면 `ArtifactNotReadyError`가 발생한다.

### 인증 라이프사이클

- 쿠키 기반 인증 (Google 비공식 API)
- 자동 갱신: CSRF 토큰 재추출 → 디스크 쿠키 재로드 → Headless Chrome (3단계)
- 2~4주마다 쿠키 만료 가능 → `nlm login` 수동 실행 필요
- Rate Limit: Free tier ~50 queries/day

### 인포그래픽 옵션

| 파라미터 | 옵션 |
|---|---|
| orientation | `landscape`, `portrait`, `square` |
| detail_level | `concise`, `standard`, `detailed` |
| infographic_style | `auto_select`, `professional`, `editorial`, `scientific`, `sketch_note`, `bento_grid`, `instructional`, `bricks`, `clay`, `anime`, `kawaii` |
| language | 언어 코드 (예: `ko`, `en`) |
| focus_prompt | 자유 텍스트 |

다운로드 출력: PNG 파일

## Error Handling

| 에러 | 원인 | 처리 |
|---|---|---|
| `TimeoutError` (소스 추가) | URL 접근 불가 또는 대용량 | wait_timeout 증가, URL 검증 |
| `ArtifactNotReadyError` | 폴링 없이 다운로드 시도 | poller로 완료 확인 후 다운로드 |
| `AuthenticationError` | 쿠키 만료 | 3단계 자동 복구, 실패 시 nlm login |
| `ServiceError` | API 호출 실패 | 재시도 로직 (3회 exponential backoff) |

## Contributing

- `src/notebooklm_tools/`는 vendored 코드 — 기능 수정/추가 금지, 원본 업데이트 시 재복사
- 모든 새 코드는 `src/pipeline/` 아래에 작성
- `notebooklm_tools.services.*`를 import하여 사용 (core/client.py 직접 import 최소화)
