"""poller 모듈 테스트."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from pipeline.poller import ArtifactNotFoundError, ArtifactTimeoutError, wait_for_artifact


@pytest.mark.asyncio
async def test_wait_completes_on_first_poll():
    """첫 폴링에서 완료 상태이면 즉시 반환."""
    mock_client = MagicMock()

    with patch("pipeline.poller.studio") as mock_studio:
        mock_studio.get_studio_status.return_value = {
            "artifacts": [
                {"artifact_id": "art-1", "status": "completed", "type": "infographic"}
            ],
            "total": 1,
            "completed": 1,
            "in_progress": 0,
        }

        result = await wait_for_artifact(
            mock_client, "nb-1", "art-1", poll_interval=1, max_wait=10
        )

    assert result["artifact_id"] == "art-1"
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_wait_polls_until_complete():
    """여러 번 폴링 후 완료."""
    mock_client = MagicMock()
    call_count = 0

    def status_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        status = "completed" if call_count >= 3 else "in_progress"
        return {
            "artifacts": [{"artifact_id": "art-1", "status": status}],
            "total": 1,
            "completed": 1 if status == "completed" else 0,
            "in_progress": 0 if status == "completed" else 1,
        }

    with patch("pipeline.poller.studio") as mock_studio:
        mock_studio.get_studio_status.side_effect = status_side_effect

        result = await wait_for_artifact(
            mock_client, "nb-1", "art-1", poll_interval=0, max_wait=10
        )

    assert result["status"] == "completed"
    assert call_count == 3


@pytest.mark.asyncio
async def test_wait_timeout():
    """타임아웃 시 ArtifactTimeoutError 발생."""
    mock_client = MagicMock()

    with patch("pipeline.poller.studio") as mock_studio:
        mock_studio.get_studio_status.return_value = {
            "artifacts": [{"artifact_id": "art-1", "status": "in_progress"}],
            "total": 1,
            "completed": 0,
            "in_progress": 1,
        }

        with pytest.raises(ArtifactTimeoutError) as exc_info:
            await wait_for_artifact(
                mock_client, "nb-1", "art-1", poll_interval=0, max_wait=0
            )

        assert "art-1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_wait_artifact_not_found():
    """아티팩트가 상태 목록에 3회 연속 없으면 ArtifactNotFoundError 발생."""
    mock_client = MagicMock()

    with patch("pipeline.poller.studio") as mock_studio:
        mock_studio.get_studio_status.return_value = {
            "artifacts": [],  # 아티팩트 없음
            "total": 0,
            "completed": 0,
            "in_progress": 0,
        }

        with pytest.raises(ArtifactNotFoundError) as exc_info:
            await wait_for_artifact(
                mock_client, "nb-1", "art-missing", poll_interval=0, max_wait=60
            )

        assert "art-missing" in str(exc_info.value)
        assert exc_info.value.consecutive == 3
