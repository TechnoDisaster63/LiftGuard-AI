"""Mirror contributed sets to a private Hugging Face dataset repo.

A host's disk is ephemeral, so each finished set is pushed as its own
commit in the background. Deletion removes the files and then squashes
the repo history, because a normal delete leaves old commits holding the
data - and "delete" has to mean deleted.

Configured by env: LIFTGUARD_CONTRIB_HF_REPO (e.g. user/liftguard-pilot-data)
and LIFTGUARD_CONTRIB_HF_TOKEN (a fine-grained token with write access to
that dataset only). Without both, contributions stay on local disk.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from pathlib import Path

log = logging.getLogger("liftguard.contrib")
RETRY_SECONDS = 120
MAX_ATTEMPTS = 5


class HubUploader:
    def __init__(self, repo_id: str, token: str, api=None, start_worker: bool = True):
        self.repo_id = repo_id
        if api is None:
            from huggingface_hub import HfApi  # optional dependency

            api = HfApi(token=token)
        self.api = api
        self.jobs: "queue.Queue[tuple]" = queue.Queue()
        self.failed: list[tuple] = []
        if start_worker:
            threading.Thread(target=self._worker, daemon=True, name="contrib-upload").start()

    def upload_set(self, folder: Path, path_in_repo: str) -> None:
        self.jobs.put(("upload", Path(folder), path_in_repo, 1))

    def delete_paths(self, paths: list[str]) -> None:
        self.jobs.put(("delete", list(paths), 1))

    def run_pending(self) -> None:
        """Process queued jobs now (tests, shutdown)."""
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                return
            self._run(job)

    def retry_failed(self) -> int:
        """Queue failed jobs again (up to MAX_ATTEMPTS each)."""
        jobs, self.failed = self.failed, []
        for job in jobs:
            self.jobs.put(job)
        return len(jobs)

    def _worker(self) -> None:
        while True:
            try:
                job = self.jobs.get(timeout=RETRY_SECONDS)
            except queue.Empty:
                self.retry_failed()
                continue
            self._run(job)

    def _run(self, job: tuple) -> None:
        try:
            if job[0] == "upload":
                _, folder, path_in_repo, _attempt = job
                if folder.exists():
                    self.api.upload_folder(repo_id=self.repo_id, repo_type="dataset", folder_path=str(folder),
                                           path_in_repo=path_in_repo, commit_message=f"Add {path_in_repo}")
            elif job[0] == "delete":
                for path in job[1]:
                    self.api.delete_folder(repo_id=self.repo_id, repo_type="dataset", path_in_repo=path,
                                           commit_message=f"Delete {path}")
                self.api.super_squash_history(repo_id=self.repo_id, repo_type="dataset",
                                              commit_message="Squash history after a contributor deletion")
        except Exception as exc:  # network, auth, a path already gone
            log.warning("contribution sync failed (%s): %s", job[0], type(exc).__name__)
            if job[-1] < MAX_ATTEMPTS:
                self.failed.append(job[:-1] + (job[-1] + 1,))


def uploader_from_env():
    repo = os.environ.get("LIFTGUARD_CONTRIB_HF_REPO", "").strip()
    token = os.environ.get("LIFTGUARD_CONTRIB_HF_TOKEN", "").strip()
    if not repo or not token:
        return None
    try:
        return HubUploader(repo, token)
    except Exception as exc:
        log.warning("contribution upload disabled: %s", type(exc).__name__)
        return None
