"""파이프라인 오케스트레이터.

전체 흐름: URL/텍스트 입력 → 소스 추가 → AI 재요약 → 인포그래픽 생성 →
          완료 대기 → 파일 다운로드 → 전달
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from notebooklm_tools.core.auth import AuthManager
from notebooklm_tools.core.client import NotebookLMClient
from notebooklm_tools.services import chat, downloads, sources, studio

from .config import PipelineConfig
from .poller import wait_for_artifact

logger = logging.getLogger(__name__)


class PipelineResult(TypedDict):
    """파이프라인 실행 결과."""

    source_id: str
    summary: str
    artifact_id: str
    file_path: str
    timestamp: str


def _create_authenticated_client(profile_name: str = "default") -> NotebookLMClient:
    """저장된 인증 프로필로 NotebookLMClient를 생성한다."""
    manager = AuthManager(profile_name)
    if not manager.profile_exists():
        raise RuntimeError(
            "NotebookLM 인증 프로필을 찾을 수 없습니다. 먼저 `nlm login`을 실행하세요."
        )

    profile = manager.load_profile()
    return NotebookLMClient(
        cookies=profile.cookies,
        csrf_token=profile.csrf_token or "",
        session_id=profile.session_id or "",
        build_label=profile.build_label or "",
    )


async def run(
    config: PipelineConfig,
    *,
    url: str | None = None,
    text: str | None = None,
    title: str | None = None,
) -> PipelineResult:
    """자동화 파이프라인 전체 실행.

    Args:
        config: 파이프라인 설정
        url: 입력 URL (url 또는 text 중 하나 필수)
        text: 입력 텍스트/웹 요약본
        title: 텍스트 소스 제목 (text 모드일 때)

    Returns:
        PipelineResult with source_id, summary, artifact_id, file_path, timestamp

    Raises:
        ValueError: url과 text 모두 없을 때
        TimeoutError: 소스 처리 또는 아티팩트 생성 타임아웃
    """
    if not url and not text:
        raise ValueError("url 또는 text 중 하나는 필수입니다")

    if not config.notebook_id:
        raise ValueError("notebook_id가 설정되지 않았습니다")

    notebook_id = config.notebook_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with _create_authenticated_client() as client:
        # ── STEP 1: 소스 추가 ──
        source_type = "url" if url else "text"
        input_display = url or (text[:80] + "..." if text and len(text) > 80 else text)
        logger.info("[STEP 1] 소스 추가 (%s): %s", source_type, input_display)

        source_result = sources.add_source(
            client,
            notebook_id,
            source_type=source_type,
            url=url,
            text=text,
            title=title or f"Pipeline Input {timestamp}",
            wait=config.source.wait,
            wait_timeout=config.source.wait_timeout,
        )
        source_id = source_result["source_id"]
        logger.info("[STEP 1] 소스 추가 완료: %s", source_id)

        # ── STEP 2: AI 재요약 ──
        logger.info("[STEP 2] AI 요약 질의")
        query_result = chat.query(client, notebook_id, config.summary.prompt)
        summary_text = query_result["answer"]
        logger.info("[STEP 2] 요약 완료 (%d자)", len(summary_text))

        # ── STEP 3: 인포그래픽 생성 시작 ──
        focus = config.infographic.focus_prompt
        if not focus and config.summary.use_as_focus:
            focus = summary_text[: config.summary.max_focus_length]

        logger.info("[STEP 3] 인포그래픽 생성 시작")
        create_result = studio.create_artifact(
            client,
            notebook_id,
            artifact_type="infographic",
            orientation=config.infographic.orientation,
            detail_level=config.infographic.detail_level,
            infographic_style=config.infographic.style,
            language=config.infographic.language,
            focus_prompt=focus,
        )
        artifact_id = create_result["artifact_id"]
        logger.info("[STEP 3] 생성 요청됨: %s (status: in_progress)", artifact_id)

        # ── STEP 4: 완료 대기 (폴링) ──
        logger.info("[STEP 4] 완료 대기 중 (최대 %d초)...", config.poller.max_wait)
        await wait_for_artifact(
            client,
            notebook_id,
            artifact_id,
            poll_interval=config.poller.interval,
            max_wait=config.poller.max_wait,
        )

        # ── STEP 5: 파일 다운로드 ──
        output_dir = Path(config.download.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = config.download.filename_template.format(timestamp=timestamp)
        file_path = str(output_dir / filename)

        logger.info("[STEP 5] 다운로드: %s", file_path)
        download_result = await downloads.download_async(
            client,
            notebook_id,
            artifact_type="infographic",
            output_path=file_path,
            artifact_id=artifact_id,
        )
        saved_path = download_result["path"]
        logger.info("[STEP 5] 저장 완료: %s", saved_path)

        return PipelineResult(
            source_id=source_id,
            summary=summary_text,
            artifact_id=artifact_id,
            file_path=saved_path,
            timestamp=timestamp,
        )
