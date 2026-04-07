# NotebookLM 자동화 파이프라인 매커니즘 설계 (초안)

> **프로젝트**: project-01-notebooklm
> **작성일**: 2026-04-07
> **상태**: DRAFT v0.1
> **기반 분석**: notebooklm-mcp-cli v0.2.x 소스 레벨 분석 완료

---

## 1. 목표

**파이프라인 흐름:**

```
트리거 수신 → 웹 요약본/URL 입력 → NotebookLM 재요약 → 인포그래픽 생성 → 파일 저장 → 전달
```

외부 트리거(Webhook, 스케줄러 등)로부터 URL 또는 웹 요약본을 수신하여,
NotebookLM의 AI 분석을 거쳐 인포그래픽을 자동 생성하고 파일로 저장 후 전달하는 것.

---

## 2. 핵심 의존성: notebooklm-mcp-cli

### 2.1 아키텍처 개요

```
notebooklm-mcp-cli
├── cli/          ← nlm 명령어 (thin wrapper)
├── mcp/          ← MCP 서버 (thin wrapper)
├── services/     ← 비즈니스 로직 ★ 자동화 진입점
│   ├── sources.py      → URL/텍스트 소스 추가
│   ├── chat.py         → AI 질의 (요약)
│   ├── studio.py       → 인포그래픽 등 아티팩트 생성
│   ├── downloads.py    → 파일 다운로드
│   ├── notebooks.py    → 노트북 CRUD
│   ├── research.py     → 웹/드라이브 리서치
│   └── pipeline.py     → 내장 파이프라인 (제한적)
└── core/
    ├── client.py       → NotebookLMClient (Google 비공식 API)
    ├── auth.py         → 쿠키 기반 인증 관리
    ├── base.py         → HTTP/RPC 인프라 + 3단계 인증 복구
    └── constants.py    → API 코드 매핑
```

### 2.2 자동화 접근 전략

| 접근 방식 | 설명 | 판정 |
|---|---|---|
| **내장 Pipeline 시스템** | YAML 기반 선언적 워크플로우 | **불가** — `download_artifact`, `studio_status` 액션 미등록 |
| **CLI (nlm) subprocess** | Shell에서 nlm 명령 순차 호출 | **가능하나 비효율** — 매 호출마다 클라이언트 초기화 |
| **services 레이어 직접 호출** | Python import로 함수 직접 사용 | **추천** — 전 단계 자동화 가능, 세밀한 제어 |

---

## 3. 파이프라인 단계별 설계

### 3.1 단계 매핑

```
[STEP 1] 트리거 수신           → 외부 구현 (webhook / cron / 파일 감시)
[STEP 2] URL/텍스트 입력       → services.sources.add_source()
[STEP 3] NotebookLM 재요약     → services.chat.query()
[STEP 4] 인포그래픽 생성 시작  → services.studio.create_artifact()
[STEP 5] 완료 대기 (폴링)     → services.studio.get_studio_status() ★ 직접 구현 필수
[STEP 6] 파일 다운로드         → services.downloads.download_async()
[STEP 7] 전달                  → 외부 구현 (Slack / Email / 파일 서버)
```

### 3.2 각 단계 상세

#### STEP 1: 트리거 수신

notebooklm-mcp-cli에는 내장 트리거 메커니즘이 없다.
외부에서 구현해야 한다.

**후보 방안:**

| 방식 | 적합 시나리오 | 복잡도 |
|---|---|---|
| Cron/스케줄러 | 정기 실행 (매일, 매주) | 낮음 |
| Webhook (FastAPI/Flask) | RSS, Slack 이벤트 등 실시간 | 중간 |
| 파일 감시 (watchdog) | 특정 폴더에 URL 목록 파일 드롭 | 낮음 |
| MCP 트리거 | Claude Code 스케줄 기능 연동 | 낮음 |

#### STEP 2: URL/텍스트 소스 추가

**서비스 함수:**
```python
# services/sources.py:101
sources.add_source(
    client,
    notebook_id,
    source_type="url",     # "url" | "text" | "drive" | "file"
    url="https://...",
    wait=True,             # 소스 처리 완료까지 대기
    wait_timeout=300.0     # 기본 120초 → 대용량 소스 대비 연장 권장
)
```

**동작 메커니즘:**
- `wait=True` 시 클라이언트 폴링 (3초 간격, `core/sources.py:45-83`)
- 소스 상태: `PROCESSING(1)` → `READY(2)` 또는 `ERROR(3)`
- 타임아웃 초과 시 `TimeoutError` 발생

**텍스트 소스 추가 (웹 요약본 직접 입력):**
```python
sources.add_source(
    client,
    notebook_id,
    source_type="text",
    text="여기에 웹 요약본 내용...",
    title="2026-04-07 웹 요약",
    wait=True
)
```

**다중 URL 일괄 추가:**
```python
sources.add_sources(
    client,
    notebook_id,
    sources=[
        {"source_type": "url", "url": "https://example.com/article1"},
        {"source_type": "url", "url": "https://example.com/article2"},
    ],
    wait=True
)
```

#### STEP 3: NotebookLM AI 재요약

**서비스 함수:**
```python
# services/chat.py:44
result = chat.query(
    client,
    notebook_id,
    query_text="이 내용의 핵심을 3가지로 요약하고 시사점을 도출해줘",
    source_ids=None,         # None이면 전체 소스 대상
    conversation_id=None,    # 후속 질문 시 이전 대화 ID 전달
    timeout=None
)
# result["answer"]       → AI 응답 텍스트
# result["sources_used"] → 참조된 소스 목록
# result["citations"]    → 인용 정보
```

**대안: 노트북 설명(자동 요약):**
```python
# 소스 전체 기반 AI 요약 (별도 질문 없이)
summary = notebooks.describe_notebook(client, notebook_id)
# summary["summary"]           → 자동 생성 요약
# summary["suggested_topics"]  → 추천 토픽 리스트
```

**채팅 설정 커스터마이징:**
```python
chat.configure_chat(
    client, notebook_id,
    goal="custom",
    custom_prompt="콘텐츠를 인포그래픽에 적합한 구조로 정리해줘. 핵심 수치, 비교 포인트, 타임라인을 포함해.",
    response_length="longer"
)
```

#### STEP 4: 인포그래픽 생성 시작

**서비스 함수:**
```python
# services/studio.py:191
result = studio.create_artifact(
    client,
    notebook_id,
    artifact_type="infographic",
    # --- 인포그래픽 전용 옵션 ---
    orientation="landscape",         # landscape | portrait | square
    detail_level="detailed",         # concise | standard | detailed
    infographic_style="professional", # 11종 (아래 표 참조)
    # --- 공통 옵션 ---
    language="ko",
    focus_prompt="핵심 데이터를 시각적으로 강조",
    source_ids=None                  # None이면 전체 소스 사용
)
# result["artifact_id"] → 생성된 아티팩트 ID
# result["status"]      → "in_progress" (항상 비동기)
```

**인포그래픽 스타일 옵션 (11종):**

| 스타일 | 설명 |
|---|---|
| `auto_select` | 자동 선택 |
| `professional` | 비즈니스/전문적 |
| `editorial` | 에디토리얼/매거진 |
| `scientific` | 과학/학술 |
| `sketch_note` | 스케치노트 |
| `bento_grid` | 벤토 그리드 |
| `instructional` | 교육/안내 |
| `bricks` | 브릭 레이아웃 |
| `clay` | 클레이 아트 |
| `anime` | 애니메이션 |
| `kawaii` | 카와이 |

> **주의**: `create_artifact`는 항상 `status: "in_progress"`를 반환한다.
> 인포그래픽이 실제 완성되기까지 수 분이 소요되며,
> 이 시간 동안 Google 서버에서 비동기로 생성이 진행된다.

#### STEP 5: 완료 대기 (폴링) -- 직접 구현 필수

> **이 단계가 전체 파이프라인의 핵심 병목이자 내장 Pipeline 시스템에 없는 부분이다.**

notebooklm-mcp-cli의 내장 파이프라인에는 `studio_status` 폴링 액션이 없으므로
반드시 직접 구현해야 한다.

**폴링 서비스 함수:**
```python
# services/studio.py:457
status_result = studio.get_studio_status(client, notebook_id)
# status_result["artifacts"]   → 아티팩트 목록
# status_result["completed"]   → 완료된 수
# status_result["in_progress"] → 진행 중인 수
```

**폴링 루프 구현 (필수):**
```python
import asyncio

async def wait_for_artifact(client, notebook_id, artifact_id,
                            poll_interval=10, max_wait=600):
    """아티팩트 생성 완료까지 폴링 대기.

    Args:
        poll_interval: 폴링 간격 (초), 기본 10초
        max_wait: 최대 대기 시간 (초), 기본 10분

    Returns:
        완료된 아티팩트 정보 dict

    Raises:
        TimeoutError: max_wait 초과 시
    """
    elapsed = 0
    while elapsed < max_wait:
        status = studio.get_studio_status(client, notebook_id)
        artifact = next(
            (a for a in status["artifacts"]
             if a.get("artifact_id") == artifact_id),
            None
        )
        if artifact and artifact["status"] == "completed":
            return artifact
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(
        f"아티팩트 {artifact_id} 생성이 {max_wait}초 내에 완료되지 않음"
    )
```

**권장 폴링 파라미터:**

| 아티팩트 유형 | 예상 생성 시간 | 권장 poll_interval | 권장 max_wait |
|---|---|---|---|
| infographic | 1~3분 | 10초 | 300초 (5분) |
| audio (podcast) | 3~10분 | 15초 | 600초 (10분) |
| video | 5~15분 | 20초 | 900초 (15분) |
| slide_deck | 1~3분 | 10초 | 300초 (5분) |
| report | 30초~1분 | 5초 | 120초 (2분) |

#### STEP 6: 파일 다운로드

**서비스 함수 (비동기):**
```python
# services/downloads.py:143
download_result = await downloads.download_async(
    client,
    notebook_id,
    artifact_type="infographic",
    output_path="./output/infographic_2026-04-07.png",
    artifact_id=artifact_id   # STEP 4에서 받은 ID
)
# download_result["path"] → 저장된 파일 경로
```

**다운로드 파일 형식:**

| artifact_type | 출력 형식 | 확장자 |
|---|---|---|
| infographic | PNG 이미지 | `.png` |
| audio | M4A 오디오 | `.m4a` |
| video | MP4 비디오 | `.mp4` |
| slide_deck | PDF 또는 PPTX | `.pdf` / `.pptx` |
| report | Markdown | `.md` |
| mind_map | JSON | `.json` |
| data_table | CSV | `.csv` |

> **전제 조건**: STEP 5의 폴링이 완료된 후에만 호출해야 한다.
> 완료 전 호출 시 `ArtifactNotReadyError` 예외가 발생한다.

#### STEP 7: 전달

notebooklm-mcp-cli에는 전달 메커니즘이 없으므로 외부 구현한다.

**후보 방안:**

| 방식 | 라이브러리 | 비고 |
|---|---|---|
| Slack | `slack_sdk` | 채널/DM으로 파일 업로드 |
| Email | `smtplib` / SendGrid | 첨부파일로 전송 |
| 로컬 파일 서버 | 파일 시스템 복사 | 가장 단순 |
| Google Drive | `google-api-python-client` | 드라이브 폴더에 업로드 |
| Webhook POST | `httpx` | 후속 시스템에 알림 |

---

## 4. 전체 파이프라인 구현 레퍼런스

```python
"""NotebookLM 자동화 파이프라인 레퍼런스 구현."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from notebooklm_tools.core.client import NotebookLMClient
from notebooklm_tools.services import (
    chat,
    downloads,
    notebooks,
    sources,
    studio,
)

logger = logging.getLogger(__name__)


async def wait_for_artifact(client, notebook_id, artifact_id,
                            poll_interval=10, max_wait=300):
    """아티팩트 완료 대기 폴링."""
    elapsed = 0
    while elapsed < max_wait:
        status = studio.get_studio_status(client, notebook_id)
        artifact = next(
            (a for a in status["artifacts"]
             if a.get("artifact_id") == artifact_id),
            None
        )
        if artifact:
            if artifact["status"] == "completed":
                logger.info("아티팩트 %s 생성 완료 (%d초)", artifact_id, elapsed)
                return artifact
            logger.debug("아티팩트 %s 상태: %s (%d초 경과)",
                         artifact_id, artifact["status"], elapsed)
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"아티팩트 생성 시간 초과 ({max_wait}초)")


async def run_pipeline(
    url: str,
    notebook_id: str,
    output_dir: str = "./output",
    *,
    summary_prompt: str = "이 내용의 핵심을 3가지로 요약해줘",
    infographic_style: str = "professional",
    orientation: str = "landscape",
    detail_level: str = "detailed",
    language: str = "ko",
) -> dict:
    """전체 자동화 파이프라인 실행.

    Args:
        url: 입력 URL 또는 웹 요약본 텍스트
        notebook_id: 대상 NotebookLM 노트북 UUID
        output_dir: 파일 저장 디렉토리
        summary_prompt: AI 요약 질의 프롬프트
        infographic_style: 인포그래픽 스타일
        orientation: 방향 (landscape/portrait/square)
        detail_level: 상세 수준 (concise/standard/detailed)
        language: 출력 언어

    Returns:
        dict with keys: summary, artifact_id, file_path, timestamp
    """
    client = NotebookLMClient()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── STEP 2: URL 소스 추가 ──
    logger.info("[STEP 2] URL 소스 추가: %s", url)
    source_result = sources.add_source(
        client, notebook_id,
        source_type="url",
        url=url,
        wait=True,
        wait_timeout=300.0
    )
    logger.info("[STEP 2] 소스 추가 완료: %s", source_result["source_id"])

    # ── STEP 3: AI 재요약 ──
    logger.info("[STEP 3] AI 요약 질의")
    query_result = chat.query(client, notebook_id, summary_prompt)
    summary_text = query_result["answer"]
    logger.info("[STEP 3] 요약 완료 (%d자)", len(summary_text))

    # ── STEP 4: 인포그래픽 생성 시작 ──
    logger.info("[STEP 4] 인포그래픽 생성 시작")
    create_result = studio.create_artifact(
        client, notebook_id,
        artifact_type="infographic",
        orientation=orientation,
        detail_level=detail_level,
        infographic_style=infographic_style,
        language=language,
        focus_prompt=summary_text[:500]  # 요약을 포커스 프롬프트로 활용
    )
    artifact_id = create_result["artifact_id"]
    logger.info("[STEP 4] 생성 시작됨: artifact_id=%s", artifact_id)

    # ── STEP 5: 완료 대기 (폴링) ──
    logger.info("[STEP 5] 완료 대기 중...")
    await wait_for_artifact(client, notebook_id, artifact_id,
                            poll_interval=10, max_wait=300)

    # ── STEP 6: 파일 다운로드 ──
    file_name = f"infographic_{timestamp}.png"
    file_path = str(output_path / file_name)
    logger.info("[STEP 6] 다운로드: %s", file_path)
    await downloads.download_async(
        client, notebook_id,
        artifact_type="infographic",
        output_path=file_path,
        artifact_id=artifact_id
    )
    logger.info("[STEP 6] 저장 완료: %s", file_path)

    return {
        "summary": summary_text,
        "artifact_id": artifact_id,
        "file_path": file_path,
        "timestamp": timestamp,
    }


# ── 진입점 ──
if __name__ == "__main__":
    result = asyncio.run(run_pipeline(
        url="https://example.com/article",
        notebook_id="YOUR_NOTEBOOK_ID",
        output_dir="./output"
    ))
    print(f"완료: {result['file_path']}")
```

---

## 5. 인증 전략

### 5.1 인증 메커니즘

notebooklm-mcp-cli는 Google NotebookLM의 **비공식 내부 API**를 사용하며,
브라우저 쿠키 기반으로 인증한다.

```
쿠키 (SID, HSID, SSID, APISID, SAPISID)
  → CSRF 토큰 (자동 추출)
  → 세션 ID (자동 추출)
  → 빌드 라벨 (자동 추출)
```

### 5.2 자동 복구 메커니즘 (3단계)

`core/base.py`에 구현된 인증 실패 시 자동 복구:

| 레이어 | 동작 | 무인 실행 | 소요 시간 |
|---|---|---|---|
| **Layer 1** | CSRF 토큰 재추출 (페이지 HTML 파싱) | 가능 | ~2초 |
| **Layer 2** | 디스크에서 쿠키 파일 재로드 | 가능 | ~1초 |
| **Layer 3** | Headless Chrome으로 쿠키 자동 갱신 | 조건부 | ~10초 |
| **실패** | `nlm login` 수동 실행 필요 | **불가** | 수동 |

**Layer 3 조건**: Chrome 프로필에 저장된 Google 로그인이 존재해야 함.

### 5.3 운영 권장사항

```
[초기 설정]
1. nlm login                     # 브라우저 팝업 → Google 로그인
2. nlm login --check             # 인증 상태 확인

[자동화 운영 중]
- Layer 1~3이 자동 처리
- 2~4주마다 쿠키 만료 가능 → 모니터링 필요

[만료 감지 시]
- AuthenticationError 로그 감시
- 알림 발송 → 관리자가 nlm login 수동 실행
```

### 5.4 Rate Limit

| 항목 | 제한 |
|---|---|
| Free tier 쿼리 | ~50회/일 |
| 429 응답 시 재시도 | 3회 exponential backoff (1s→2s→4s) |
| `Retry-After` 헤더 파싱 | **미구현** (현재 코드에 없음) |

---

## 6. 리스크 분석

### 6.1 기술적 리스크

| 리스크 | 심각도 | 발생 확률 | 대응 |
|---|---|---|---|
| 쿠키 만료로 인증 실패 | **높음** | 2~4주 주기 | 모니터링 + 수동 재인증 알림 |
| 인포그래픽 생성 시간 초과 | 중간 | 간헐적 | max_wait 충분히 설정 (300초+) |
| Google API 변경/차단 | **높음** | 예측 불가 | 비공식 API 의존 불가피, 버전 고정 |
| Rate limit 초과 | 중간 | 일일 50회 초과 시 | 큐잉 + 일일 실행 횟수 제한 |
| 소스 처리 실패 | 낮음 | URL 접근 불가 시 | 에러 핸들링 + 재시도 로직 |

### 6.2 운영 리스크

| 리스크 | 대응 |
|---|---|
| Chrome 업데이트로 CDP 호환성 깨짐 | notebooklm-mcp-cli 업데이트 추적 |
| Google 계정 보안 이벤트 (비정상 접근 감지) | 전용 Google 계정 사용 권장 |
| NotebookLM 서비스 중단 | 헬스체크 + 재시도 큐 |

---

## 7. 내장 Pipeline 확장 방안 (선택적)

현재 내장 Pipeline의 `VALID_ACTIONS`에 누락된 액션을 추가하면
YAML 선언형 파이프라인으로도 활용 가능하다.

**필요한 추가 액션:**

```python
# services/pipeline.py 수정 제안
VALID_ACTIONS = {
    "source_add",
    "notebook_query",
    "studio_create",
    "notebook_create",
    "notebook_delete",
    # ── 추가 필요 ──
    "studio_wait",          # 아티팩트 완료 대기 (폴링)
    "download_artifact",    # 파일 다운로드
    "research_start",       # 웹 리서치 시작
    "research_import",      # 리서치 결과 임포트
}
```

**YAML 파이프라인 예시 (확장 후):**

```yaml
name: url-to-infographic
description: URL 입력 → 요약 → 인포그래픽 생성 → PNG 다운로드
steps:
  - action: source_add
    params:
      type: url
      url: "$INPUT_URL"
      wait: true
  - action: notebook_query
    params:
      query: "핵심 내용을 3가지로 요약해줘"
  - action: studio_create
    params:
      artifact_type: infographic
      orientation: landscape
      detail_level: detailed
      infographic_style: professional
      language: ko
  - action: studio_wait          # 현재 미구현
    params:
      poll_interval: 10
      max_wait: 300
  - action: download_artifact    # 현재 미구현
    params:
      artifact_type: infographic
      output_path: "./output/$TIMESTAMP_infographic.png"
```

> **참고**: 이 확장은 upstream PR로 기여하거나, 로컬 fork에서 구현할 수 있다.

---

## 8. 구현 우선순위

### Phase 1: 최소 동작 파이프라인 (MVP)

- [ ] Python 스크립트로 services 직접 호출 방식 구현
- [ ] `wait_for_artifact` 폴링 함수 구현
- [ ] 기본 에러 핸들링 (인증 실패, 타임아웃)
- [ ] 로컬 파일 저장 (./output/ 디렉토리)
- [ ] CLI 수동 트리거 (`python run_pipeline.py --url "..."`)

### Phase 2: 트리거 + 전달

- [ ] 트리거 메커니즘 선택 및 구현 (Webhook / Cron)
- [ ] 전달 메커니즘 구현 (Slack / Email)
- [ ] 인증 만료 모니터링 + 알림

### Phase 3: 안정화 + 확장

- [ ] Rate limit 대응 큐잉 시스템
- [ ] 다중 아티팩트 지원 (인포그래픽 + 리포트 + 오디오)
- [ ] 실행 이력 로깅 + 대시보드
- [ ] 내장 Pipeline 확장 기여 (선택)

---

## 부록 A: 환경 설정

```bash
# 1. notebooklm-mcp-cli 설치
uv tool install notebooklm-mcp-cli

# 2. 인증
nlm login
nlm login --check

# 3. 노트북 확인
nlm notebook list

# 4. 테스트 실행
nlm source add <notebook_id> --url "https://example.com"
nlm studio create <notebook_id> --type infographic --confirm
nlm studio status <notebook_id>
nlm download infographic <notebook_id>
```

## 부록 B: 주요 소스 파일 참조

| 파일 | 역할 | 핵심 함수 |
|---|---|---|
| `services/sources.py` | 소스 추가 | `add_source()`, `add_sources()` |
| `services/chat.py` | AI 질의 | `query()`, `configure_chat()` |
| `services/studio.py` | 아티팩트 생성 | `create_artifact()`, `get_studio_status()` |
| `services/downloads.py` | 파일 다운로드 | `download_async()`, `download_sync()` |
| `services/notebooks.py` | 노트북 관리 | `create_notebook()`, `list_notebooks()` |
| `services/pipeline.py` | 내장 파이프라인 | `pipeline_run()`, `pipeline_create()` |
| `core/base.py` | HTTP/인증 인프라 | `_call_rpc()`, `_refresh_auth_tokens()` |
| `core/constants.py` | API 코드 매핑 | `INFOGRAPHIC_STYLES`, `INFOGRAPHIC_ORIENTATIONS` |
