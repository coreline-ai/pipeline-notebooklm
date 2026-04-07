"""전달 메커니즘 — 생성된 파일을 목적지로 전달.

지원 방식:
- file: 로컬 파일 시스템 (이미 저장된 상태이므로 경로만 반환)
- slack: Slack 채널에 파일 업로드 (선택적 의존성)
- email: 이메일 첨부파일 전송 (선택적 의존성)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

from .config import DeliveryConfig

logger = logging.getLogger(__name__)


class DeliveryResult(TypedDict):
    """전달 결과."""

    method: str
    destination: str
    success: bool
    message: str


async def deliver(
    config: DeliveryConfig,
    file_path: str,
    summary: str = "",
) -> DeliveryResult:
    """설정에 따라 파일을 전달한다.

    Args:
        config: 전달 설정
        file_path: 전달할 파일 경로
        summary: 요약 텍스트 (메시지 본문에 포함)

    Returns:
        DeliveryResult
    """
    method = config.method

    if method == "file":
        return _deliver_file(file_path)
    elif method == "slack":
        return await _deliver_slack(config, file_path, summary)
    elif method == "email":
        return await _deliver_email(config, file_path, summary)
    else:
        return DeliveryResult(
            method=method,
            destination="unknown",
            success=False,
            message=f"지원하지 않는 전달 방식: {method}",
        )


def _deliver_file(file_path: str) -> DeliveryResult:
    """로컬 파일 전달 (이미 저장됨)."""
    exists = Path(file_path).exists()
    return DeliveryResult(
        method="file",
        destination=file_path,
        success=exists,
        message=f"파일 저장 완료: {file_path}" if exists else f"파일 없음: {file_path}",
    )


async def _deliver_slack(
    config: DeliveryConfig,
    file_path: str,
    summary: str,
) -> DeliveryResult:
    """Slack 채널에 파일 업로드."""
    try:
        from slack_sdk import WebClient
    except ImportError:
        return DeliveryResult(
            method="slack",
            destination="",
            success=False,
            message="slack-sdk가 설치되지 않았습니다. "
            "pip install notebooklm-auto-pipeline[slack]",
        )

    token = config.slack.get("token", "")
    channel = config.slack.get("channel", "")

    if not token or not channel:
        return DeliveryResult(
            method="slack",
            destination=channel,
            success=False,
            message="Slack token 또는 channel이 설정되지 않았습니다",
        )

    client = WebClient(token=token)
    comment = summary[:300] if summary else "NotebookLM 인포그래픽 자동 생성 결과"

    try:
        client.files_upload_v2(
            channel=channel,
            file=file_path,
            title=Path(file_path).name,
            initial_comment=comment,
        )
        logger.info("Slack 전달 완료: %s → %s", file_path, channel)
        return DeliveryResult(
            method="slack",
            destination=channel,
            success=True,
            message=f"Slack #{channel}에 전달 완료",
        )
    except Exception as e:
        logger.error("Slack 전달 실패: %s", e)
        return DeliveryResult(
            method="slack",
            destination=channel,
            success=False,
            message=f"Slack 전달 실패: {e}",
        )


async def _deliver_email(
    config: DeliveryConfig,
    file_path: str,
    summary: str,
) -> DeliveryResult:
    """이메일로 파일 첨부 전송."""
    import email.mime.base
    import email.mime.multipart
    import email.mime.text
    from email import encoders

    try:
        import aiosmtplib
    except ImportError:
        return DeliveryResult(
            method="email",
            destination="",
            success=False,
            message="aiosmtplib가 설치되지 않았습니다. "
            "pip install notebooklm-auto-pipeline[email]",
        )

    smtp_host = config.email.get("smtp_host", "")
    smtp_port = config.email.get("smtp_port", 587)
    username = config.email.get("username", "")
    password = config.email.get("password", "")
    to_addr = config.email.get("to", "")
    subject = config.email.get("subject", "NotebookLM 인포그래픽")

    if not all([smtp_host, username, password, to_addr]):
        return DeliveryResult(
            method="email",
            destination=to_addr,
            success=False,
            message="이메일 설정이 불완전합니다 (smtp_host, username, password, to 필요)",
        )

    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = username
    msg["To"] = to_addr
    msg["Subject"] = subject

    body = summary[:1000] if summary else "첨부된 인포그래픽을 확인해주세요."
    msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

    filepath = Path(file_path)
    with open(filepath, "rb") as f:
        part = email.mime.base.MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filepath.name}"')
    msg.attach(part)

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=username,
            password=password,
            start_tls=True,
        )
        logger.info("이메일 전달 완료: %s → %s", file_path, to_addr)
        return DeliveryResult(
            method="email",
            destination=to_addr,
            success=True,
            message=f"{to_addr}로 이메일 전달 완료",
        )
    except Exception as e:
        logger.error("이메일 전달 실패: %s", e)
        return DeliveryResult(
            method="email",
            destination=to_addr,
            success=False,
            message=f"이메일 전달 실패: {e}",
        )
