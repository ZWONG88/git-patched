import os
import time
import uuid

import boto3
from botocore.exceptions import ClientError

JOBS_TABLE = os.getenv("JOBS_TABLE", "pr-guardian-jobs")
# Keep these aligned with template.yaml: one-hour delivery, 180-second worker.
QUEUE_SECONDS = 3600
RUN_SECONDS = 240  # Allow a minute beyond the Lambda execution timeout.


def _now():
    return int(time.time())


def _table():
    return boto3.resource("dynamodb").Table(JOBS_TABLE)


def create_review_job(pr_url=None):
    now = _now()
    job_id = str(uuid.uuid4())
    item = {
        "job_id": job_id,
        "status": "queued",
        "stage": "fetching",
        "created_at": now,
        "queue_deadline": now + QUEUE_SECONDS,
        "expires_at": now + 24 * 3600,
    }
    if pr_url is not None:
        item["pr_url"] = pr_url
    _table().put_item(Item=item, ConditionExpression="attribute_not_exists(job_id)")
    return job_id


def get_review_job(job_id):
    job = _table().get_item(Key={"job_id": job_id}, ConsistentRead=True).get("Item")
    if not job:
        return None
    now = _now()
    if job.get("expires_at", now + 1) <= now:
        return None
    # Derive timeout status while reading. No extra API write permission or
    # scheduled AWS service is needed; the stored row is left for TTL cleanup.
    deadline = None
    message = None
    if job.get("status") == "queued":
        deadline = job.get("queue_deadline")
        message = "The review did not start in time. Please submit a new review."
    elif job.get("status") == "running":
        deadline = job.get("run_deadline")
        message = "The review exceeded its time limit. Please submit a new review."
    if deadline is not None and deadline <= now:
        return {**job, "status": "failed", "stage": "failed", "error_message": message}
    return job


def _active_condition():
    return (
        "attribute_exists(job_id) AND #s IN (:queued, :running) "
        "AND (attribute_not_exists(run_deadline) OR run_deadline > :now) "
        "AND (attribute_not_exists(queue_deadline) OR #s <> :queued OR queue_deadline > :now) "
        "AND (attribute_not_exists(expires_at) OR expires_at > :now)"
    )


def _active_values():
    return {":queued": "queued", ":running": "running", ":now": _now()}


def update_review_job(job_id, stage, status="running"):
    if status != "running":
        raise ValueError("Progress updates must have running status.")
    _table().update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :running, stage = :stage",
        ConditionExpression=_active_condition(),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={**_active_values(), ":stage": stage},
    )


def complete_review_job(job_id, result):
    _table().update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :completed, stage = :stage, review_result = :result",
        ConditionExpression=_active_condition() + " AND #s = :running",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            **_active_values(), ":completed": "completed", ":stage": "complete", ":result": result,
        },
    )


def fail_review_job(job_id, message):
    _table().update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :failed, stage = :stage, error_message = :message",
        ConditionExpression=_active_condition(),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            **_active_values(), ":failed": "failed", ":stage": "failed", ":message": message,
        },
    )


def claim_review_job(job_id):
    now = _now()
    try:
        _table().update_item(
            Key={"job_id": job_id},
            UpdateExpression=(
                "SET #s = :running, stage = :stage, started_at = :now, run_deadline = :deadline"
            ),
            ConditionExpression=(
                "#s = :queued "
                "AND (attribute_not_exists(queue_deadline) OR queue_deadline > :now) "
                "AND (attribute_not_exists(expires_at) OR expires_at > :now)"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":running": "running", ":queued": "queued", ":stage": "fetching",
                ":now": now, ":deadline": now + RUN_SECONDS,
            },
        )
        return True
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
