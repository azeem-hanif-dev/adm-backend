import asyncio
import datetime
import logging

from bson import ObjectId
from pymongo import ReturnDocument

from db import campaign_jobs_coll
from dependencies import ai, email_sender
from services import process_campaign_job_batch


logger = logging.getLogger("campaign-worker")


async def _fetch_next_pending_job():
    """
    Atomically fetch the next pending job and mark it as claimed.
    """
    return await campaign_jobs_coll.find_one_and_update(
        {"status": "pending"},
        {
            "$set": {
                "status": "claimed",
                "updated_at": datetime.datetime.utcnow(),
            }
        },
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def run_worker_loop(poll_interval_seconds: int = 5):
    """
    Continuous worker loop that polls for pending campaign jobs.
    """
    logger.info("Campaign worker started")

    while True:
        try:
            job = await _fetch_next_pending_job()
            if not job:
                await asyncio.sleep(poll_interval_seconds)
                continue

            job_id = str(job["_id"])
            logger.info(f"Picked up job {job_id} / campaign {job.get('campaign_id')}")
            await process_campaign_job_batch(job_id, batch_size=20, ai=ai, email_sender=email_sender)
        except Exception as e:
            logger.exception(f"Worker loop error: {e}")
            await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_worker_loop())

