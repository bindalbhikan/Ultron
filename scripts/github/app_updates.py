"""Publish completed app packages to Cloudflare R2 through the authenticated app API."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ultron.core import http

PLATFORMS = {"ULTRON.apk": "android", "ULTRON-Windows.zip": "windows",
             "ULTRON-macOS.zip": "macos", "ULTRON-Linux.tar.gz": "linux"}


def publish_updates(files: dict[str, Path], *, api: str, token: str, version: str, build: int) -> None:
    """Use bounded multipart uploads, then atomically advance each platform's manifest."""
    with http.client(headers={"Authorization": f"Bearer {token}"}, timeout=180, follow_redirects=False) as client:
        for name, platform in PLATFORMS.items():
            path = files.get(name)
            if path is None:
                continue
            with path.open("rb") as stream:
                sha = hashlib.file_digest(stream, "sha256").hexdigest()
            response = client.post(f"{api}/api/releases/upload", json={
                "platform": platform, "version": version, "build": build,
                "size": path.stat().st_size, "sha256": sha,
            })
            if response.status_code != 200:
                raise RuntimeError(f"Cloudflare update storage refused {platform} ({response.status_code}); no new manifest published.")
            upload = response.json()
            parts = []
            with path.open("rb") as stream:
                while chunk := stream.read(10_000_000):
                    response = client.put(f"{api}/api/releases/upload", params={**upload, "part": len(parts) + 1},
                                          content=chunk, headers={"Content-Type": "application/octet-stream"})
                    if response.status_code != 200:
                        raise RuntimeError(f"Cloudflare update upload failed for {platform} ({response.status_code}).")
                    parts.append(response.json())
            response = client.post(f"{api}/api/releases/complete", params=upload, json={"parts": parts})
            if response.status_code != 200:
                raise RuntimeError(f"Cloudflare update publication failed for {platform} ({response.status_code}).")
            print(f"{name}: Cloudflare update manifest published")
