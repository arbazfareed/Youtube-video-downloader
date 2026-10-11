from __future__ import annotations

import hmac
import logging
import os
import secrets
import shutil
import threading
import tempfile
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from bandwidth import GlobalBandwidthLimiter
from download_engine import (
    DownloadCancelled,
    RetryPolicy,
    download_url,
    parse_custom_headers,
)
from handoff import make_qr_png, mobile_handoff_url
try:
    from torrent_engine import is_torrent_url
except ModuleNotFoundError as error:
    if error.name != "torrent_engine":
        raise

    def is_torrent_url(url: str) -> bool:
        return urlsplit(url).scheme.lower() == "magnet"


_TOKEN = os.environ.get("SMART_DOWNLOADER_API_TOKEN") or secrets.token_urlsafe(32)
_SECURITY = HTTPBearer(auto_error=False)
_HANDOFF_SECURITY = HTTPBearer(auto_error=False)
_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="download-api")
_JOBS: dict[str, "ApiJob"] = {}
_JOBS_LOCK = threading.Lock()
_BANDWIDTH_LIMITER = GlobalBandwidthLimiter()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    logging.getLogger("uvicorn.error").info(
        "Smart Downloader API Bearer token: %s", _TOKEN
    )
    yield


app = FastAPI(
    title="Smart Downloader API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=_lifespan,
)


class JobRequest(BaseModel):
    url: str = Field(min_length=1, max_length=8192)
    output: str = Field(default="downloads", min_length=1, max_length=4096)
    source: str = "auto"
    mode: str = "video"
    quality: str = "1080p"
    playlist_scope: str = "auto (from link)"
    speed: str = "fast"
    cap: int | None = Field(default=None, gt=0)
    proxy: str = ""
    cookies: str = "none"
    headers: dict[str, str] = Field(default_factory=dict)
    retry_attempts: int = Field(default=10, ge=1, le=20)
    retry_base_delay: float = Field(default=1.0, ge=0, le=60)
    retry_max_delay: float = Field(default=30.0, ge=0, le=300)
    auto_extract: bool = False
    cloud_provider: str = "local"
    cloud_folder: str = ""


@dataclass
class ApiJob:
    id: str
    request: JobRequest
    status: str = "queued"
    progress: float | None = None
    details: str = ""
    result: str | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    resume_event: threading.Event = field(default_factory=threading.Event)
    handoff_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    handoff_expires_at: float = field(default_factory=lambda: time.time() + 86400)

    def public_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.request.url,
            "status": self.status,
            "progress": self.progress,
            "details": self.details,
            "result": self.result,
            "error": self.error,
        }


def _authorized(
    credentials: HTTPAuthorizationCredentials | None = Depends(_SECURITY),
) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer" or not hmac.compare_digest(
        credentials.credentials, _TOKEN
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid Bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _get_job(job_id: str) -> ApiJob:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def _run_job(job: ApiJob) -> None:
    job.status = "running"

    def report(state: str, percent: float | None, details: str) -> None:
        job.status = "paused" if not job.resume_event.is_set() else "running"
        job.progress = percent
        job.details = f"{state}: {details}" if details else state

    try:
        request = job.request
        job.result = download_url(
            request.url,
            Path(request.output).expanduser(),
            request.source,
            request.mode,
            request.quality,
            request.playlist_scope,
            job.cancel_event,
            report,
            request.speed,
            job.resume_event,
            request.cap,
            _BANDWIDTH_LIMITER,
            f"api:{job.id}",
            request.proxy,
            request.cookies,
            custom_headers=request.headers,
            retry_policy=RetryPolicy(
                request.retry_attempts,
                request.retry_base_delay,
                request.retry_max_delay,
            ),
        )
        if request.auto_extract:
            from extract import extract_archive

            extracted = extract_archive(Path(job.result))
            if extracted is not None:
                job.result = str(extracted)
        if request.cloud_provider.lower() != "local":
            from cloud_storage import select_upload_source, upload_path

            try:
                remote_paths = upload_path(
                    select_upload_source(Path(job.result), Path(request.output)),
                    request.cloud_provider,
                    request.cloud_folder,
                )
            except Exception as error:
                raise RuntimeError(
                    f"Cloud upload failed; the downloaded copy remains at {request.output}: {error}"
                ) from error
            job.result = "; ".join(remote_paths)
            try:
                shutil.rmtree(request.output)
            except OSError as error:
                job.details = (
                    f"Upload complete; local staging copy remains at "
                    f"{request.output}: {error}"
                )
        job.status = "completed"
        job.progress = 100.0
    except DownloadCancelled as error:
        job.status = "cancelled"
        job.error = str(error)
    except Exception as error:
        job.status = "failed"
        job.error = str(error)


def _validate_request(request: JobRequest) -> None:
    source = request.source.lower()
    try:
        torrent = is_torrent_url(request.url)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Enter a valid download URL.") from error
    if torrent:
        if (
            request.proxy
            or request.cookies.lower() not in {"", "none", "off"}
            or request.headers
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Proxy, browser cookies, and custom headers are not supported "
                    "for torrent jobs."
                ),
            )
    elif (
        source in {"torrent", "torrent/magnet"}
        or urlsplit(request.url).scheme.lower() not in {"http", "https"}
        or not urlsplit(request.url).hostname
    ):
        raise HTTPException(status_code=422, detail="Enter a valid HTTP(S) URL.")
    if source not in {"auto", "direct file", "supported site", "torrent", "torrent/magnet"}:
        raise HTTPException(status_code=422, detail="Unknown download source.")
    if request.speed.lower() not in {"balanced", "fast", "maximum"}:
        raise HTTPException(status_code=422, detail="Unknown download speed.")
    if request.cloud_provider.lower() not in {"local", "s3", "google drive", "dropbox"}:
        raise HTTPException(status_code=422, detail="Unknown cloud destination.")
    if request.cloud_provider.lower() != "local":
        from cloud_storage import is_configured

        try:
            if not is_configured(request.cloud_provider):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Configure {request.cloud_provider} in the desktop app "
                        "before creating cloud jobs."
                    ),
                )
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if request.cookies.lower() not in {"none", "off", "chrome", "firefox", "edge", "brave"}:
        raise HTTPException(status_code=422, detail="Unknown browser cookie source.")
    if request.proxy:
        from proxy import parse_proxy_list

        try:
            parse_proxy_list(request.proxy)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        request.headers = parse_custom_headers(request.headers)
        RetryPolicy(
            request.retry_attempts,
            request.retry_base_delay,
            request.retry_max_delay,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/jobs", dependencies=[Depends(_authorized)])
def list_jobs() -> list[dict[str, Any]]:
    with _JOBS_LOCK:
        return [job.public_record() for job in _JOBS.values()]


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(_authorized)])
def create_job(request: JobRequest) -> dict[str, Any]:
    _validate_request(request)
    if request.cloud_provider.lower() != "local":
        request.output = tempfile.mkdtemp(prefix="smart-downloader-cloud-")
    elif not Path(request.output).expanduser().is_absolute():
        request.output = str(Path(request.output).expanduser().resolve())
    job = ApiJob(secrets.token_urlsafe(12), request)
    job.resume_event.set()
    with _JOBS_LOCK:
        _JOBS[job.id] = job
    _EXECUTOR.submit(_run_job, job)
    return job.public_record()


@app.get("/jobs/{job_id}", dependencies=[Depends(_authorized)])
def get_job(job_id: str) -> dict[str, Any]:
    return _get_job(job_id).public_record()


@app.post("/jobs/{job_id}/cancel", dependencies=[Depends(_authorized)])
def cancel_job(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    if job.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="This job has already finished.")
    job.cancel_event.set()
    job.resume_event.set()
    job.status = "cancelling"
    return job.public_record()


@app.post("/jobs/{job_id}/pause", dependencies=[Depends(_authorized)])
def pause_job(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    if job.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Only queued or running jobs can be paused.")
    job.resume_event.clear()
    job.status = "paused"
    return job.public_record()


@app.post("/jobs/{job_id}/resume", dependencies=[Depends(_authorized)])
def resume_job(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    if job.status != "paused":
        raise HTTPException(status_code=409, detail="Only paused jobs can be resumed.")
    job.resume_event.set()
    job.status = "running"
    return job.public_record()


def _handoff_job(job_id: str, credentials: HTTPAuthorizationCredentials | None) -> ApiJob:
    job = _get_job(job_id)
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or time.time() >= job.handoff_expires_at
        or not hmac.compare_digest(credentials.credentials, job.handoff_token)
    ):
        raise HTTPException(status_code=401, detail="This phone link is invalid or expired.")
    return job


def _mobile_record(job: ApiJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
    }


@app.post("/jobs/{job_id}/handoff/qr", dependencies=[Depends(_authorized)])
def create_handoff_qr(job_id: str) -> Response:
    job = _get_job(job_id)
    host = os.environ.get("SMART_DOWNLOADER_API_HOST", "127.0.0.1")
    if host in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(
            status_code=409,
            detail="Restart the API with SMART_DOWNLOADER_API_HOST=0.0.0.0 to enable phone access.",
        )
    try:
        port = int(os.environ.get("SMART_DOWNLOADER_API_PORT", "8765"))
        url = mobile_handoff_url(job.id, job.handoff_token, port)
        image = make_qr_png(url)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail="Could not determine the PC's LAN address.") from error
    return Response(content=image, media_type="image/png")


@app.get("/mobile", response_class=HTMLResponse)
def mobile_page() -> str:
    return Path(__file__).with_name("mobile.html").read_text(encoding="utf-8")


@app.get("/mobile.js")
def mobile_script() -> Response:
    script = Path(__file__).with_name("mobile.js").read_text(encoding="utf-8")
    return Response(content=script, media_type="application/javascript")


@app.get("/mobile/jobs/{job_id}")
def get_mobile_job(
    job_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(_HANDOFF_SECURITY),
) -> dict[str, Any]:
    return _mobile_record(_handoff_job(job_id, credentials))


@app.post("/mobile/jobs/{job_id}/{action}")
def control_mobile_job(
    job_id: str,
    action: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(_HANDOFF_SECURITY),
) -> dict[str, Any]:
    job = _handoff_job(job_id, credentials)
    if action == "pause":
        if job.status not in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="Only queued or running jobs can be paused.")
        job.resume_event.clear()
        job.status = "paused"
    elif action == "resume":
        if job.status != "paused":
            raise HTTPException(status_code=409, detail="Only paused jobs can be resumed.")
        job.resume_event.set()
        job.status = "running"
    elif action == "cancel":
        if job.status in {"completed", "failed", "cancelled"}:
            raise HTTPException(status_code=409, detail="This job has already finished.")
        job.cancel_event.set()
        job.resume_event.set()
        job.status = "cancelling"
    else:
        raise HTTPException(status_code=404, detail="Unknown job action.")
    return _mobile_record(job)


def main() -> None:
    import uvicorn

    host = os.environ.get("SMART_DOWNLOADER_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SMART_DOWNLOADER_API_PORT", "8765"))
    if host not in {"127.0.0.1", "::1", "localhost"} and not os.environ.get(
        "SMART_DOWNLOADER_API_TOKEN"
    ):
        raise RuntimeError(
            "Set SMART_DOWNLOADER_API_TOKEN before binding the API beyond localhost."
        )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
