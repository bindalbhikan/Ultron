"""Files kept on Google Drive, read and written through the Drive API.

The master is updated in place (same file id, same link), so Drive for desktop
syncs the new version down to G:\\My Drive like any other edit, and Drive keeps
the previous versions under "Manage versions".

The service account needs Editor access to every workbook a bot writes and
Viewer access to the lookup sheets (share them with the client_email from the
key JSON). upload() only replaces a file this run downloaded, and refuses when
someone changed it on Drive in the meantime.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from google.auth.exceptions import TransportError
from google.auth.transport.requests import AuthorizedSession

from .gauth import drive_credentials, oauth_configured

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FIELDS = "id,name,mimeType,modifiedTime,md5Checksum,size,webViewLink,capabilities/canEdit"
RETRY_PAUSES = (10, 30, 0)   # seconds after each of the three tries


class DriveError(RuntimeError):
    pass


class DriveConflict(DriveError):
    """The file was changed on Drive since this run downloaded it."""


def _passing(r) -> bool:
    """An answer that says try again: a 5xx, or Drive's rate limit (429, 403 rateLimitExceeded)."""
    return r.status_code >= 500 or r.status_code == 429 or (r.status_code == 403 and "ateLimitExceeded" in r.text)


def _with_retries(send, what: str):
    """send() again on a passing answer, a timeout or a dropped connection (three tries, 3 Nov 2026: a
    502 from Drive ended a whole run). The last answer is returned; a last dropped connection raises DriveError."""
    for attempt, pause in enumerate(RETRY_PAUSES, 1):
        try:
            r = send()
            if not _passing(r) or not pause:
                return r
            problem = f"HTTP {r.status_code}"
        except (OSError, ConnectionError, TransportError) as exc:   # timeouts, dropped connections, also on the token refresh
            problem = f"{type(exc).__name__}: {str(exc)[:120]}"
            if not pause:
                raise DriveError(f"Drive {what} failed {attempt} times: {problem}") from exc
        log.warning("Drive %s: %s (try %d of %d); trying again", what, problem, attempt, len(RETRY_PAUSES))
        time.sleep(pause)
    raise AssertionError("unreachable")


class RetrySession(AuthorizedSession):
    """Every read tried again by itself, also for code that uses a folder's .http directly. A write is not: only the
    upload methods here know when sending it twice is safe."""

    def request(self, method, url, *args, **kwargs):
        send = lambda: super(RetrySession, self).request(method, url, *args, **kwargs)  # noqa: E731
        return _with_retries(send, f"read of {url.split('?')[0][-60:]}") if method.upper() == "GET" else send()


def session() -> AuthorizedSession:
    return RetrySession(drive_credentials(SCOPES))


class _Saved:
    """The answer of an upload that was not sent: Drive already has this content."""
    status_code, ok, text = 200, True, ""

    def __init__(self, meta: dict):
        self.meta = meta

    def json(self) -> dict:
        return self.meta


class DriveFile:
    def __init__(self, file_id: str, http: AuthorizedSession | None = None):
        self.file_id = file_id
        self.http = http or session()
        self.meta: dict = {}

    def _check(self, r, what: str):
        if r.status_code == 404:
            raise DriveError(f"Drive file {self.file_id} not found - is it shared with the service account?")
        if not r.ok:
            raise DriveError(f"Drive {what} failed: HTTP {r.status_code} {r.text[:300]}")
        return r

    def metadata(self) -> dict:
        r = self.http.get(f"{API}/{self.file_id}", timeout=60, params={"fields": FIELDS, "supportsAllDrives": "true"})
        return self._check(r, "metadata").json()

    @property
    def name(self) -> str:
        return self.meta.get("name", self.file_id)

    @property
    def url(self) -> str:
        return self.meta.get("webViewLink", f"https://drive.google.com/file/d/{self.file_id}/view")

    def download(self, dest: Path, need_edit: bool = False) -> Path:
        self.meta = self.metadata()
        if self.meta.get("mimeType") != XLSX:
            raise DriveError(f"{self.name} is {self.meta.get('mimeType')}, expected an .xlsx file")
        if need_edit and not self.meta.get("capabilities", {}).get("canEdit"):
            raise DriveError(f"Service account can read but not edit {self.name} - share it as Editor")
        r = self.http.get(f"{API}/{self.file_id}", timeout=300, params={"alt": "media", "supportsAllDrives": "true"})
        self._check(r, "download")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        log.info("Downloaded %s from Drive (%s bytes, modified %s)",
                 self.name, len(r.content), self.meta.get("modifiedTime"))
        return dest

    def upload(self, src: Path) -> None:
        """Replace the file's content. Refuses if someone changed it since download()."""
        if not self.meta:
            raise DriveError(f"{self.name}: download() it before upload(), so a change made on Drive "
                             "during the run is never overwritten")
        body = src.read_bytes()
        mine = hashlib.md5(body).hexdigest()  # noqa: S324 - Drive's own change check, not security

        def send():
            # checked before every try; a 5xx can still have saved the file: our own content there means done
            now = self.metadata()
            if now.get("md5Checksum") == mine:
                return _Saved(now)
            if now.get("md5Checksum") != self.meta.get("md5Checksum"):
                raise DriveConflict(f"{now.get('name')} was changed on Drive during the run "
                                    f"(modified {now.get('modifiedTime')}); not overwriting it. Run again.")
            return self.http.patch(f"{UPLOAD}/{self.file_id}", data=body, timeout=300,
                                   params={"uploadType": "media", "supportsAllDrives": "true", "fields": FIELDS},
                                   headers={"Content-Type": XLSX})

        self.meta = self._check(_with_retries(send, f"upload of {self.name}"), "upload").json()
        log.info("Uploaded %s to Drive (modified %s)", self.name, self.meta.get("modifiedTime"))


class DriveFolder:
    """A Drive folder: list, read and write files in it by name (used for whole report folders)."""
    FOLDER = "application/vnd.google-apps.folder"

    def __init__(self, folder_id: str, http: AuthorizedSession | None = None):
        self.folder_id = folder_id
        self.http = http or session()

    def _check(self, r, what: str):
        if not r.ok:
            raise DriveError(f"Drive {what} failed: HTTP {r.status_code} {r.text[:300]}")
        return r

    def children(self) -> dict[str, dict]:
        """name -> {id, name, mimeType} of the files and folders directly in this folder."""
        out, token = {}, None
        while True:
            params = {"q": f"'{self.folder_id}' in parents and trashed=false", "pageSize": 1000,
                      "fields": "nextPageToken,files(id,name,mimeType,modifiedTime)",
                      "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
            if token:
                params["pageToken"] = token
            data = self._check(self.http.get(API, params=params, timeout=60), "folder listing").json()
            out.update({f["name"]: f for f in data.get("files", [])})
            token = data.get("nextPageToken")
            if not token:
                return out

    def subfolder(self, name: str, create: bool = False) -> "DriveFolder | None":
        found = self.children().get(name)
        if found and found["mimeType"] == self.FOLDER:
            return DriveFolder(found["id"], self.http)
        if not create:
            return None
        r = self.http.post(API, params={"supportsAllDrives": "true", "fields": "id"}, timeout=60,
                           json={"name": name, "mimeType": self.FOLDER, "parents": [self.folder_id]})
        log.info("Created Drive folder %s", name)
        return DriveFolder(self._check(r, "folder create").json()["id"], self.http)

    def download(self, name: str, dest: Path) -> Path | None:
        """The named file into dest; None when the folder has no such file."""
        found = self.children().get(name)
        if not found or found["mimeType"] == self.FOLDER:
            return None
        r = self.http.get(f"{API}/{found['id']}", params={"alt": "media", "supportsAllDrives": "true"}, timeout=600)
        self._check(r, f"download of {name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        log.info("Downloaded %s from Drive (%d bytes)", name, len(r.content))
        return dest

    def download_all(self, dest: Path) -> list[Path]:
        """Every file (not sub folders) of this folder into dest."""
        return [p for name, f in self.children().items() if f["mimeType"] != self.FOLDER
                for p in [self.download(name, dest / name)] if p]

    def put(self, src: Path, mime: str = "application/octet-stream") -> str:
        """Upload src under its own name: the file of that name is replaced (same id), else created.
        A service account cannot create files in a personal Drive (no storage quota): new files
        need the owner's OAuth token (gauth.drive_credentials, scripts/google/oauth_token.py)."""
        found = self.children().get(src.name)
        if not found and not oauth_configured():
            raise DriveError(f"{src.name} cannot be created on Drive: GOOGLE_OAUTH_CLIENT_ID / _SECRET / "
                             "_REFRESH_TOKEN not set (python scripts/google/oauth_token.py)")
        file_id = self._upload(src, mime, found["id"] if found else None)
        log.info("Uploaded %s to Drive", src.name)
        return file_id

    def _upload(self, src: Path, mime: str, file_id: str | None) -> str:
        """A resumable upload: replaces file_id's content, or creates src.name in this folder.
        Start and send are tried again together, on a passing answer or a dropped connection (three tries)."""
        params = {"uploadType": "resumable", "supportsAllDrives": "true", "fields": "id"}
        tries = [0]

        def send():
            target = file_id
            if not target and tries[0]:     # the try that failed may still have created the file: never a second one
                made = self.children().get(src.name)
                target = made["id"] if made else None
            tries[0] += 1
            if target:
                r = self.http.patch(f"{UPLOAD}/{target}", params=params, json={}, timeout=60, headers={"X-Upload-Content-Type": mime})
            else:
                r = self.http.post(UPLOAD, params=params, json={"name": src.name, "parents": [self.folder_id]}, timeout=60,
                                   headers={"X-Upload-Content-Type": mime})
            if not r.ok:
                return r
            return self.http.put(r.headers["Location"], data=src.read_bytes(), timeout=900, headers={"Content-Type": mime})

        return self._check(_with_retries(send, f"upload of {src.name}"), f"upload of {src.name}").json()["id"]
