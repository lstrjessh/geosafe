"""Bounded single-process jobs with explicit expiry; no database is required."""

import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .exports import write_results

TTL = 3600
ROOT = Path(tempfile.gettempdir()) / "geosafe-jobs"
ROOT.mkdir(exist_ok=True)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="geosafe-analysis")
lock = threading.RLock()
slots = threading.BoundedSemaphore(2)
jobs = {}


def create(work):
    with lock:
        expired = [
            id_
            for id_, job in jobs.items()
            if job["status"] in ["succeeded", "failed"]
            and time.time() - job["updated"] > TTL
        ]
        for id_ in expired:
            jobs.pop(id_, None)
            shutil.rmtree(ROOT / id_, ignore_errors=True)
    if not slots.acquire(blocking=False):
        raise RuntimeError(
            "The analysis queue is full. Try again after the current job finishes."
        )
    id_ = uuid.uuid4().hex
    with lock:
        jobs[id_] = {
            "id": id_,
            "status": "queued",
            "message": "Waiting for the analysis worker",
            "updated": time.time(),
        }

    def run():
        def progress(message):
            with lock:
                jobs[id_].update(status="running", message=message, updated=time.time())

        try:
            progress("Preparing analysis")
            result = work(progress)
            progress("Preparing map previews and GeoTIFF exports")
            output = write_results(result, ROOT / id_)
            with lock:
                jobs[id_].update(
                    status="succeeded",
                    message="Analysis complete",
                    result=output,
                    updated=time.time(),
                )
        except Exception as error:
            with lock:
                jobs[id_].update(
                    status="failed", message=str(error)[:700], updated=time.time()
                )
            shutil.rmtree(ROOT / id_, ignore_errors=True)
        finally:
            slots.release()

    executor.submit(run)
    return id_


def get(id_):
    with lock:
        job = jobs.get(id_)
        if not job:
            return None
        if (
            job["status"] in ["succeeded", "failed"]
            and time.time() - job["updated"] > TTL
        ):
            return None
        return dict(job)
