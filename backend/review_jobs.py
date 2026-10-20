
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

JOBS_TABLE = os.getenv("JOBS_TABLE", "pr-guardian-jobs")


def create_review_job(pr_url=None):
    job_id = str(uuid.uuid4())
    expires = int(
        (datetime.now(timezone.utc) + timedelta(hours=24)).timestamp()
    )

    item = {
        "job_id": job_id,
        "status": "queued",
        "stage": "fetching",
        "expires_at": expires,
    }

    if pr_url is not None:
        item["pr_url"] = pr_url

    table = boto3.resource("dynamodb").Table(JOBS_TABLE)

    table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(job_id)",
    )

    return job_id


def update_review_job(job_id, stage, status="running"):
    table = boto3.resource("dynamodb").Table(JOBS_TABLE)

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :status, stage = :stage",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": status,
            ":stage": stage,
        },
    )


def get_review_job(job_id):
    table = boto3.resource("dynamodb").Table(JOBS_TABLE)
    response = table.get_item(Key={"job_id": job_id})
    return response.get("Item")


def complete_review_job(job_id, result):
    table = boto3.resource("dynamodb").Table(JOBS_TABLE)

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=(
            "SET #s = :status, stage = :stage, "
            "review_result = :result"
        ),
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": "completed",
            ":stage": "complete",
            ":result": result,
        },
    )


def fail_review_job(job_id, message):
    table = boto3.resource("dynamodb").Table(JOBS_TABLE)

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=(
            "SET #s = :status, error_message = :message"
        ),
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": "failed",
            ":message": message,
        },
    )


def claim_review_job(job_id):
    table = boto3.resource("dynamodb").Table(JOBS_TABLE)

    try:
        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression=(
                "SET #s = :running, stage = :stage"
            ),
            ConditionExpression="#s = :queued",
            ExpressionAttributeNames={
                "#s": "status",
            },
            ExpressionAttributeValues={
                ":running": "running",
                ":queued": "queued",
                ":stage": "fetching",
            },
        )
        return True

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")

        if code == "ConditionalCheckFailedException":
            return False

        raise
