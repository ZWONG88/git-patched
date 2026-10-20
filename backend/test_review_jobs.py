
import os

import boto3
from moto import mock_aws

from review_jobs import (
    create_review_job,
    update_review_job,
    get_review_job,
)


def test_review_jobs():
    os.environ["AWS_DEFAULT_REGION"] = "us-west-2"

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-west-2")

        dynamodb.create_table(
            TableName="pr-guardian-jobs",
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        job_id = create_review_job()
        job = get_review_job(job_id)

        assert job["status"] == "queued"
        assert job["stage"] == "fetching"
        print("Job creation: PASSED")

        update_review_job(job_id, "generating")
        job = get_review_job(job_id)

        assert job["status"] == "running"
        assert job["stage"] == "generating"
        print("Progress update: PASSED")


if __name__ == "__main__":
    test_review_jobs()
