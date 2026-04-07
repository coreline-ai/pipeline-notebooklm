# 🚀 Pipeline NotebookLM

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](./pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-7%20passed-22C55E?logo=pytest&logoColor=white)](./tests)
[![E2E](https://img.shields.io/badge/E2E-verified-16A34A?logo=githubactions&logoColor=white)](#-현재-변경-사항)
[![Vendor](https://img.shields.io/badge/vendor-notebooklm--mcp--cli%200.5.16-6D28D9?logo=git&logoColor=white)](#-원본-출처)
[![Status](https://img.shields.io/badge/status-active-2563EB?logo=github&logoColor=white)](#-현재-변경-사항)

> URL 또는 텍스트 요약본을 입력받아 **NotebookLM 재요약 → 인포그래픽 생성 → PNG 저장/전달**까지 자동화하는 독립 실행형 파이프라인입니다.

---

## ✨ 핵심 기능

- `URL` 또는 `텍스트`를 NotebookLM 소스로 자동 등록
- NotebookLM 기반 AI 재요약
- 인포그래픽 생성 요청 후 완료까지 폴링
- 결과 PNG 다운로드 및 로컬 저장
- `file / slack / email` 전달 방식 지원
- `manual / watch / webhook` 실행 모드 지원

---

## 🗺️ 아키텍처

```text
Input(URL/Text)
  -> pipeline.core.run()
     -> sources.add_source()
     -> chat.query()
     -> studio.create_artifact()
     -> poller.wait_for_artifact()
     -> downloads.download_async()
     -> delivery.deliver()
```

### 디렉토리 구성

```text
pipeline-notebooklm/
├── configs/
│   └── default.yaml
├── scripts/
│   └── run_pipeline.py
├── src/
│   ├── notebooklm_tools/   # vendored source
│   └── pipeline/           # project-specific automation layer
├── tests/
├── AUTOMATION_MECHANISM.md
├── CLAUDE.md
└── pyproject.toml
```

---

## ⚡ 빠른 실행

### 1) 의존성 설치

```bash
uv sync
```

### 2) NotebookLM 인증

```bash
nlm login
nlm login --check
```

### 3) Notebook ID 확인

```bash
nlm notebook list
```

### 4) 수동 실행

#### URL 입력

```bash
uv run python scripts/run_pipeline.py \
  --url "https://example.com/article" \
  --notebook-id "YOUR_NOTEBOOK_ID" \
  -v
```

#### 텍스트 입력

```bash
uv run python scripts/run_pipeline.py \
  --text "여기에 요약본 내용..." \
  --notebook-id "YOUR_NOTEBOOK_ID" \
  -v
```

#### 텍스트 파일 입력

```bash
uv run python scripts/run_pipeline.py \
  --text-file input.txt \
  --notebook-id "YOUR_NOTEBOOK_ID" \
  -v
```

### 5) 결과물

기본 설정 기준 결과 파일:

```text
output/infographic_YYYYMMDD_HHMMSS.png
```

---

## 🔌 실행 모드

### Manual

```bash
uv run python scripts/run_pipeline.py --url "https://..." --notebook-id "..."
```

### Watch

```bash
uv run python scripts/run_pipeline.py --mode watch --notebook-id "..."
```

- 기본 감시 경로: `./watch`
- `.txt` 파일 내용이 URL이면 URL 모드, 아니면 텍스트 모드로 처리

### Webhook

추가 의존성 설치:

```bash
uv sync --extra webhook
```

서버 실행:

```bash
uv run python scripts/run_pipeline.py --mode webhook --notebook-id "..."
```

요청 예시:

```bash
curl -X POST http://127.0.0.1:8080/trigger \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/article"}'
```

---

## 🧪 현재 변경 사항

### Latest Update — `2026-04-07`

- ✅ **실제 E2E 파이프라인 검증 완료**
  - 텍스트 입력
  - NotebookLM 요약
  - 인포그래픽 생성
  - PNG 다운로드/저장
- ✅ **인증 프로필 자동 로드 버그 수정**
  - `pipeline.core`가 이제 저장된 NotebookLM 인증 프로필을 읽어서 클라이언트를 생성합니다.
- ✅ **실행 안정성 검증**
  - `pytest` 통과
  - CLI help 동작 확인
  - 실제 NotebookLM 환경에서 생성 완료 확인

### 최신 커밋

- Commit: [`9b248ad`](https://github.com/coreline-ai/pipeline-notebooklm/commit/9b248ad51d61532acfe9b6bfb56240985849019e)
- Message: `fix: load NotebookLM auth profile in pipeline client`

---

## 🧩 원본 출처

이 프로젝트는 아래 오픈소스의 일부를 **vendor** 하여 사용합니다.

- 원본 프로젝트: [`jacob-bd/notebooklm-mcp-cli`](https://github.com/jacob-bd/notebooklm-mcp-cli)
- 사용 버전: `0.5.16`
- 가져온 범위:
  - `src/notebooklm_tools/core/`
  - `src/notebooklm_tools/services/`
  - `src/notebooklm_tools/utils/`

### 이 프로젝트에서 추가한 레이어

- `src/pipeline/config.py` — 설정 로드/검증
- `src/pipeline/core.py` — 파이프라인 오케스트레이션
- `src/pipeline/poller.py` — 인포그래픽 완료 대기
- `src/pipeline/trigger.py` — 수동/감시/webhook 트리거
- `src/pipeline/delivery.py` — 저장/Slack/Email 전달

즉, **NotebookLM 도구 레이어는 원본 기반**, **자동화 파이프라인 레이어는 이 저장소에서 별도 구현**되었습니다.

---

## ⚠️ 주의 사항

- NotebookLM 공식 공개 API가 아닌 **비공식 내부 동작 기반**입니다.
- 인증 세션이 만료되면 다시 `nlm login` 이 필요합니다.
- 인포그래픽 생성은 비동기이므로 반드시 `poller`로 완료 확인 후 다운로드해야 합니다.
- `src/notebooklm_tools/` 는 vendored 코드이므로 기능 수정은 최소화하고, 일반 로직은 `src/pipeline/` 아래에서 확장하는 것을 권장합니다.

---

## 📚 참고 문서

- [`CLAUDE.md`](./CLAUDE.md)
- [`AUTOMATION_MECHANISM.md`](./AUTOMATION_MECHANISM.md)
- [`configs/default.yaml`](./configs/default.yaml)

