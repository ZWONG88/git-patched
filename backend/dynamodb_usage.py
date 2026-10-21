
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException


def claim_dynamodb_review():
    table_name = os.getenv("DYNAMODB_TABLE", "pr-guardian-usage")
    try:
        limit = int(os.getenv("DAILY_REVIEW_LIMIT", "20"))
    except ValueError:
        raise HTTPException(status_code=503, detail="Review capacity is not configured correctly.") from None
    if limit <= 0:
        raise HTTPException(status_code=429, detail="Daily AI review limit reached. Try again tomorrow.")
    today = datetime.now(timezone.utc).date().isoformat()

    table = boto3.resource("dynamodb").Table(table_name)

    try:
        table.update_item(
            Key={"date": today},
            UpdateExpression=(
                "SET review_count = if_not_exists(review_count, :zero) + :one"
            ),
            ConditionExpression=(
                "attribute_not_exists(review_count) OR review_count < :limit"
            ),
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":limit": limit,
            },
        )

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")

        if code == "ConditionalCheckFailedException":
            raise HTTPException(
                status_code=429,
                detail="Daily AI review limit reached. Try again tomorrow.",
            )

        raise HTTPException(
            status_code=503,
            detail="Usage tracking is temporarily unavailable.",
        )
