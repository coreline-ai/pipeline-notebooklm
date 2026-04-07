"""아티팩트 완료 대기 폴링.

notebooklm-mcp-cli의 studio.create_artifact()는 항상 status="in_progress"를
반환한다. 다운로드 전에 반드시 이 모듈의 폴링으로 완료를 확인해야 한다.
완료 전 download_async() 호출 시 ArtifactNotReadyError가 발생한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from notebooklm_tools.services import studio

if TYPE_CHECKING:
    from notebooklm_tools.core.client import NotebookLMClient

logger = logging.getLogger(__name__)


class ArtifactTimeoutError(TimeoutError):
    """아티팩트 생성이 제한 시간 내에 완료되지 않음."""

    def __init__(self, artifact_id: str, max_wait: int):
        self.artifact_id = artifact_id
        self.max_wait = max_wait
        super().__init__(
            f"아티팩트 {artifact_id} 생성이 {max_wait}초 내에 완료되지 않음"
        )


class ArtifactNotFoundError(RuntimeError):
    """아티팩트가 상태 목록에서 연속으로 발견되지 않음."""

    def __init__(self, artifact_id: str, consecutive: int):
        self.artifact_id = artifact_id
        self.consecutive = consecutive
        super().__init__(
            f"아티팩트 {artifact_id}가 {consecutive}회 연속 상태 목록에서 발견되지 않음 "
            f"(삭제되었거나 잘못된 ID일 수 있음)"
        )


async def wait_for_artifact(
    client: NotebookLMClient,
    notebook_id: str,
    artifact_id: str,
    *,
    poll_interval: int = 10,
    max_wait: int = 300,
) -> dict:
    """아티팩트 생성 완료까지 폴링 대기.

    studio.get_studio_status()를 주기적으로 호출하여
    대상 artifact_id의 status가 "completed"가 될 때까지 대기한다.

    Args:
        client: 인증된 NotebookLMClient
        notebook_id: 노트북 UUID
        artifact_id: 대기할 아티팩트 ID
        poll_interval: 폴링 간격 (초)
        max_wait: 최대 대기 시간 (초)

    Returns:
        완료된 아티팩트 정보 dict

    Raises:
        ArtifactTimeoutError: max_wait 초과 시
        ArtifactNotFoundError: 아티팩트가 3회 연속 상태 목록에서 발견되지 않을 때
    """
    elapsed = 0
    not_found_streak = 0
    max_not_found = 3

    while elapsed < max_wait:
        status_result = studio.get_studio_status(client, notebook_id)

        found = False
        for artifact in status_result["artifacts"]:
            if artifact.get("artifact_id") == artifact_id:
                found = True
                not_found_streak = 0
                current_status = artifact.get("status", "unknown")

                if current_status == "completed":
                    logger.info(
                        "아티팩트 %s 완료 (소요: %d초)", artifact_id, elapsed
                    )
                    return artifact

                logger.debug(
                    "아티팩트 %s 상태: %s (%d/%d초)",
                    artifact_id,
                    current_status,
                    elapsed,
                    max_wait,
                )
                break

        if not found:
            not_found_streak += 1
            logger.warning(
                "아티팩트 %s 를 상태 목록에서 찾을 수 없음 (%d/%d)",
                artifact_id,
                not_found_streak,
                max_not_found,
            )
            if not_found_streak >= max_not_found:
                raise ArtifactNotFoundError(artifact_id, not_found_streak)

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise ArtifactTimeoutError(artifact_id, max_wait)
