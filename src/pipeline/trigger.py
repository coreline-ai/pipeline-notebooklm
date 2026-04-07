"""트리거 메커니즘 — 파이프라인 실행을 시작하는 외부 이벤트 수신.

지원 방식:
- manual: CLI에서 직접 실행
- watch: 특정 디렉토리에 파일 생성 감시
- webhook: HTTP POST 수신 (FastAPI, 선택적 의존성)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator, TypedDict

from .config import TriggerConfig

logger = logging.getLogger(__name__)


class TriggerEvent(TypedDict):
    """트리거 이벤트."""

    source: str  # "manual" | "watch" | "webhook"
    url: str | None
    text: str | None
    metadata: dict


def manual_event(
    url: str | None = None,
    text: str | None = None,
) -> TriggerEvent:
    """수동 트리거 이벤트 생성."""
    return TriggerEvent(
        source="manual",
        url=url,
        text=text,
        metadata={},
    )


async def watch_directory(config: TriggerConfig) -> AsyncIterator[TriggerEvent]:
    """디렉토리 감시 트리거.

    지정 디렉토리에 새 파일이 생성되면 파일 내용(URL 목록 또는 텍스트)을
    읽어 트리거 이벤트를 발생시킨다.
    처리된 파일은 .done 확장자로 이름이 변경된다.

    Args:
        config: 트리거 설정 (watch.directory, watch.pattern)

    Yields:
        TriggerEvent for each new file
    """
    watch_dir = Path(config.watch.get("directory", "./watch"))
    pattern = config.watch.get("pattern", "*.txt")

    watch_dir.mkdir(parents=True, exist_ok=True)
    logger.info("파일 감시 시작: %s/%s", watch_dir, pattern)
    seen: set[str] = set()

    while True:
        for filepath in sorted(watch_dir.glob(pattern)):
            name = filepath.name
            if name in seen or name.endswith(".done"):
                continue

            seen.add(name)
            content = filepath.read_text(encoding="utf-8").strip()

            if content.startswith("http://") or content.startswith("https://"):
                event = TriggerEvent(
                    source="watch",
                    url=content.split("\n")[0].strip(),
                    text=None,
                    metadata={"file": str(filepath)},
                )
            else:
                event = TriggerEvent(
                    source="watch",
                    url=None,
                    text=content,
                    metadata={"file": str(filepath)},
                )

            logger.info("파일 감지: %s", name)

            # 처리 완료 표시
            done_path = filepath.with_suffix(filepath.suffix + ".done")
            filepath.rename(done_path)

            yield event

        await asyncio.sleep(5)


async def webhook_server(config: TriggerConfig) -> AsyncIterator[TriggerEvent]:
    """Webhook HTTP 서버 트리거.

    POST /trigger 로 JSON body를 수신하여 파이프라인을 실행한다.
    FastAPI 의존성이 필요하다 (pip install notebooklm-auto-pipeline[webhook]).

    Expected JSON body:
        {"url": "https://..."} 또는 {"text": "요약본..."}

    Args:
        config: 트리거 설정 (webhook.host, webhook.port, webhook.path)

    Yields:
        TriggerEvent for each POST request
    """
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError:
        raise ImportError(
            "webhook 트리거를 사용하려면 fastapi와 uvicorn이 필요합니다. "
            "설치: pip install notebooklm-auto-pipeline[webhook]"
        )

    app = FastAPI(title="NotebookLM Pipeline Trigger")
    event_queue: asyncio.Queue[TriggerEvent] = asyncio.Queue()

    path = config.webhook.get("path", "/trigger")

    @app.post(path)
    async def receive_trigger(body: dict) -> dict:
        event = TriggerEvent(
            source="webhook",
            url=body.get("url"),
            text=body.get("text"),
            metadata=body.get("metadata", {}),
        )
        await event_queue.put(event)
        logger.info("Webhook 수신: %s", body.get("url") or "(text)")
        return {"status": "accepted"}

    host = config.webhook.get("host", "0.0.0.0")
    port = config.webhook.get("port", 8080)

    server_config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(server_config)

    # 서버를 백그라운드로 실행
    asyncio.create_task(server.serve())
    logger.info("Webhook 서버 시작: http://%s:%d%s", host, port, path)

    while True:
        event = await event_queue.get()
        yield event
