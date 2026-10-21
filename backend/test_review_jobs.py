
import os

import boto3
from moto import mock_aws

from review_jobs import (
    create_review_job,
    update_review_job,
    get_review_job,
    complete_review_job,
    fail_review_job,
    claim_review_job,
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

        result = {
            "repository": "python/cpython",
            "pull_request": 1,
            "review": "Example AI review for local testing.",
        }

        complete_review_job(job_id, result)
        job = get_review_job(job_id)

        assert job["status"] == "completed"
        assert job["stage"] == "complete"
        assert job["review_result"] == result
        print("Completed review storage: PASSED")

        failed_job_id = create_review_job()
        fail_review_job(failed_job_id, "Example failure")
        failed_job = get_review_job(failed_job_id)

        assert failed_job["status"] == "failed"
        assert failed_job["error_message"] == "Example failure"
        print("Failed review storage: PASSED")


        duplicate_job_id = create_review_job()

        first_claim = claim_review_job(duplicate_job_id)
        second_claim = claim_review_job(duplicate_job_id)

        assert first_claim is True
        assert second_claim is False

        claimed_job = get_review_job(duplicate_job_id)

        assert claimed_job["status"] == "running"
        print("Duplicate job protection: PASSED")



if __name__ == "__main__":
    test_review_jobs()
