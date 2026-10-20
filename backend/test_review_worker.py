import os
import socket
from unittest.mock import patch

# Dummy values apply only to this test process.
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-west-2"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["USE_DYNAMODB"] = "true"
os.environ["JOBS_TABLE"] = "pr-guardian-jobs"

import boto3
from moto import mock_aws


def block_network(*args, **kwargs):
    raise AssertionError("This test must not make network calls.")


def test_review_worker():
    # Prevent main.py from loading your real .env file.
    # Block real network connections throughout the simulation.
    with (
        patch("dotenv.load_dotenv", return_value=False),
        patch.object(socket.socket, "connect", block_network),
        patch.object(socket.socket, "connect_ex", block_network),
        patch("socket.create_connection", side_effect=block_network),
        mock_aws(),
    ):
        import review_jobs
        import review_worker

        dynamodb = boto3.resource(
            "dynamodb",
            region_name="us-west-2",
        )

        table = dynamodb.create_table(
            TableName="pr-guardian-jobs",
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        pr_url = "https://github.com/example/demo/pull/1"
        job_id = review_jobs.create_review_job(pr_url=pr_url)

        job = review_jobs.get_review_job(job_id)
        assert job["status"] == "queued"
        assert job["pr_url"] == pr_url
        print("Queued job setup: PASSED")

        reviewer_calls = []

        expected_result = {
            "repository": "example/demo",
            "pull_request": 1,
            "review": "Fake review: no external services were called.",
        }

        def fake_reviewer(received_url, report=None):
            reviewer_calls.append(received_url)
            assert received_url == pr_url
            assert callable(report)

            # The worker must claim the job before reviewing.
            running_job = review_jobs.get_review_job(job_id)
            assert running_job["status"] == "running"
            print("Worker claimed job: PASSED")

            report("generating")
            running_job = review_jobs.get_review_job(job_id)
            assert running_job["status"] == "running"
            assert running_job["stage"] == "generating"
            print("Worker progress saved: PASSED")

            report("formatting")
            return expected_result

        # Keep the real processor, but inject the fake reviewer.
        # This also exercises handler({"job_id": ...}, context).
        real_processor = review_worker.process_review_job

        def process_with_fake_reviewer(received_job_id):
            return real_processor(
                received_job_id,
                reviewer=fake_reviewer,
            )

        with patch.object(
            review_worker,
            "process_review_job",
            side_effect=process_with_fake_reviewer,
        ):
            response = review_worker.handler(
                {"job_id": job_id},
                None,
            )

            assert response == {
                "job_id": job_id,
                "status": "completed",
            }
            print("Lambda handler response: PASSED")

            completed_job = review_jobs.get_review_job(job_id)
            assert completed_job["status"] == "completed"
            assert completed_job["stage"] == "complete"
            assert completed_job["review_result"] == expected_result
            assert reviewer_calls == [pr_url]
            print("Completed result saved: PASSED")

            # Your current worker rejects completed jobs.
            try:
                review_worker.handler({"job_id": job_id}, None)
            except ValueError as error:
                assert str(error) == "Review job is not queued."
            else:
                raise AssertionError("Duplicate invocation was accepted.")

            assert reviewer_calls == [pr_url]
            assert (
                review_jobs.get_review_job(job_id)["review_result"]
                == expected_result
            )
            print("Duplicate invocation blocked: PASSED")

        print("All worker simulation checks passed.")


if __name__ == "__main__":
    test_review_worker()