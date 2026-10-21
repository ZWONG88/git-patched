
import logging

from fastapi import HTTPException

from main import execute_ai_review
from review_jobs import (
    get_review_job,
    claim_review_job,
    update_review_job,
    complete_review_job,
    fail_review_job,
)

logger = logging.getLogger(__name__)

ALLOWED_STAGES = {
    "fetching",
    "checking",
    "preparing",
    "generating",
    "formatting",
    "cached",
}


def process_review_job(job_id, reviewer=execute_ai_review):
    if not job_id or not isinstance(job_id, str):
        raise ValueError("A valid job ID is required.")

    job = get_review_job(job_id)

    if not job:
        raise ValueError("Review job does not exist.")

    if job.get("status") != "queued":
        raise ValueError("Review job is not queued.")

    pr_url = job.get("pr_url")

    if not pr_url:
        raise ValueError("Review job is missing its pull request URL.")
    

    if not claim_review_job(job_id):
        raise ValueError("Review job has already been claimed.")


    def report(stage):
        if stage in ALLOWED_STAGES:
            update_review_job(job_id, stage)

    try:
        result = reviewer(pr_url, report=report)

        if (
            not isinstance(result, dict)
            or not isinstance(result.get("review"), str)
            or not result["review"].strip()
        ):
            raise RuntimeError("Review returned no usable result.")

        complete_review_job(job_id, result)
        return {"job_id": job_id, "status": "completed"}

    except HTTPException as error:
        message = (
            "Review capacity is currently full. Please try again later."
            if error.status_code == 429
            else "The review could not be completed. Please try again later."
        )
        fail_review_job(job_id, message)
        return {"job_id": job_id, "status": "failed"}

    except Exception as error:
        logger.error("Review job failed: %s (%s)", job_id, type(error).__name__)
        fail_review_job(
            job_id,
            "The AI review failed. Please try again later.",
        )
        return {"job_id": job_id, "status": "failed"}


def handler(event, context):
    if not isinstance(event, dict):
        raise ValueError("Invalid worker event.")

    job_id = event.get("job_id")

    return process_review_job(job_id)
