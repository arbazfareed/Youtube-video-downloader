from __future__ import annotations

import json
import posixpath
from pathlib import Path

import keyring


_SERVICE = "SmartDownloader.Cloud"


def _set_secret(key: str, value: str) -> None:
    try:
        keyring.set_password(_SERVICE, key, value)
    except keyring.errors.KeyringError as error:
        raise RuntimeError(f"Could not access the operating system credential store: {error}") from error


def _get_secret(key: str) -> str | None:
    try:
        return keyring.get_password(_SERVICE, key)
    except keyring.errors.KeyringError as error:
        raise RuntimeError(f"Could not access the operating system credential store: {error}") from error


def save_credentials(provider: str, credentials: dict[str, str]) -> None:
    normalized = provider.strip().lower()
    normalized = {"amazon s3": "s3"}.get(normalized, normalized)
    required = {
        "s3": {"access_key", "secret_key", "bucket", "region"},
        "google drive": {"client_config"},
        "dropbox": {"access_token", "refresh_token", "app_key", "app_secret"},
    }.get(normalized)
    if required is None:
        raise ValueError("Choose Amazon S3, Google Drive, or Dropbox.")
    missing = required - credentials.keys()
    if missing:
        raise ValueError(f"Missing cloud account settings: {', '.join(sorted(missing))}.")
    _set_secret(normalized, json.dumps(credentials))


def is_configured(provider: str) -> bool:
    normalized = provider.strip().lower()
    normalized = {"amazon s3": "s3"}.get(normalized, normalized)
    value = _get_secret(normalized)
    if not value:
        return False
    credentials = json.loads(value)
    return isinstance(credentials, dict)


def _credentials(provider: str) -> dict[str, str]:
    value = _get_secret(provider)
    if not value:
        raise RuntimeError(f"Configure {provider} under Cloud setup before uploading.")
    result = json.loads(value)
    if not isinstance(result, dict):
        raise RuntimeError(f"Saved {provider} credentials are invalid. Configure them again.")
    return result


def _remote_path(prefix: str, relative_path: str) -> str:
    parts = [part for part in prefix.replace("\\", "/").split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Cloud folder path cannot contain '.' or '..' segments.")
    return posixpath.join(*parts, relative_path.replace("\\", "/")) if parts else relative_path.replace("\\", "/")


def select_upload_source(
    result_path: Path | str,
    staging_directory: Path | str,
) -> Path:
    result = Path(result_path).expanduser().resolve()
    staging = Path(staging_directory).expanduser().resolve()
    if result.is_file() and staging.is_dir():
        files = [item for item in staging.rglob("*") if item.is_file()]
        if len(files) > 1:
            return staging
    return result


def _upload_s3(path: Path, relative_path: str, prefix: str) -> str:
    import boto3

    credentials = _credentials("s3")
    key = _remote_path(prefix, relative_path)
    client = boto3.client(
        "s3",
        region_name=credentials["region"],
        aws_access_key_id=credentials["access_key"],
        aws_secret_access_key=credentials["secret_key"],
    )
    client.upload_file(str(path), credentials["bucket"], key)
    return f"s3://{credentials['bucket']}/{key}"


def _google_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = _credentials("google drive")
    token_json = _get_secret("google-drive-token")
    credentials = Credentials.from_authorized_user_info(json.loads(token_json)) if token_json else None
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if credentials is None or not credentials.valid:
        flow = InstalledAppFlow.from_client_config(
            json.loads(settings["client_config"]),
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        credentials = flow.run_local_server(port=0, open_browser=True)
    _set_secret("google-drive-token", credentials.to_json())
    return credentials


def _upload_google_drive(path: Path, relative_path: str, parent_id: str) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    credentials = _google_credentials()
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    body: dict[str, object] = {"name": Path(relative_path).name}
    if parent_id:
        body["parents"] = [parent_id]
    result = drive.files().create(
        body=body,
        media_body=MediaFileUpload(str(path), resumable=True),
        fields="id,webViewLink",
    ).execute()
    return result.get("webViewLink") or f"Google Drive file {result['id']}"


def _upload_dropbox(path: Path, relative_path: str, prefix: str) -> str:
    import dropbox
    from dropbox.files import WriteMode

    credentials = _credentials("dropbox")
    target = "/" + _remote_path(prefix, relative_path).lstrip("/")
    client = dropbox.Dropbox(
        oauth2_refresh_token=credentials["refresh_token"],
        app_key=credentials["app_key"],
        app_secret=credentials["app_secret"],
    )
    chunk_size = 8 * 1024 * 1024
    with path.open("rb") as source:
        first_chunk = source.read(chunk_size)
        if path.stat().st_size <= chunk_size:
            result = client.files_upload(first_chunk, target, mode=WriteMode.overwrite)
        else:
            session = client.files_upload_session_start(first_chunk)
            cursor = dropbox.files.UploadSessionCursor(
                session_id=session.session_id, offset=len(first_chunk)
            )
            while path.stat().st_size - cursor.offset > chunk_size:
                chunk = source.read(chunk_size)
                client.files_upload_session_append_v2(chunk, cursor)
                cursor.offset += len(chunk)
            result = client.files_upload_session_finish(
                source.read(),
                cursor,
                dropbox.files.CommitInfo(path=target, mode=WriteMode.overwrite),
            )
    return f"Dropbox {result.path_display}"


def upload_path(path: Path, provider: str, remote_folder: str = "") -> list[str]:
    source = path.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Downloaded file or folder is missing: {source}")
    files = sorted(item for item in source.rglob("*") if item.is_file()) if source.is_dir() else [source]
    if not files:
        raise RuntimeError("There are no downloaded files to upload.")

    results = []
    for file_path in files:
        relative = file_path.name if source.is_file() else file_path.relative_to(source).as_posix()
        normalized = provider.strip().lower()
        if normalized == "s3":
            remote = _upload_s3(file_path, relative, remote_folder)
        elif normalized == "google drive":
            remote = _upload_google_drive(file_path, relative, remote_folder)
        elif normalized == "dropbox":
            remote = _upload_dropbox(file_path, relative, remote_folder)
        else:
            raise ValueError("Choose Amazon S3, Google Drive, or Dropbox.")
        results.append(remote)
    return results
