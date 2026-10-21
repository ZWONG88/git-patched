import os
import socket
from unittest.mock import patch

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-west-2"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["USE_DYNAMODB"] = "true"
os.environ["JOBS_TABLE"] = "pr-guardian-jobs"
os.environ["DEMO_ACCESS_KEY"] = "local-test-key-only"

import boto3
from fastapi.testclient import TestClient
from moto import mock_aws


def block_network(*args, **kwargs):
    raise AssertionError("This test must not make network calls.")


def test_review_job_status():
    with (
        patch("dotenv.load_dotenv", return_value=False),
        patch.object(socket.socket, "connect", block_network),
        patch.object(socket.socket, "connect_ex", block_network),
        patch("socket.create_connection", side_effect=block_network),
        mock_aws(),
    ):
        from main import app
        import review_jobs

        dynamodb = boto3.resource(
            "dynamodb",
            region_name="us-west-2",
        )

        dynamodb.create_table(
            TableName="pr-guardian-jobs",
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        job_id = review_jobs.create_review_job(
            pr_url="https://github.com/example/demo/pull/1"
        )
        path = f"/review-jobs/{job_id}"
        headers = {"x-demo-key": "local-test-key-only"}

        with TestClient(app) as client:
            # Authentication failures must not read the database.
            with patch.object(
                review_jobs,
                "get_review_job",
                side_effect=AssertionError("Unauthorized database read"),
            ):
                response = client.get(path)
                assert response.status_code == 401
                print("Missing key rejected: PASSED")

                response = client.get(
                    path,
                    headers={"x-demo-key": "incorrect-key"},
                )
                assert response.status_code == 401
                print("Incorrect key rejected: PASSED")

            response = client.get(path, headers=headers)
            assert response.status_code == 200
            assert response.json() == {
                "job_id": job_id,
                "status": "queued",
                "stage": "fetching",
            }
            print("Authenticated queued status: PASSED")

            review_jobs.update_review_job(job_id, "generating")

            response = client.get(path, headers=headers)
            assert response.status_code == 200
            assert response.json()["status"] == "running"
            assert response.json()["stage"] == "generating"
            print("Running status: PASSED")

            result = {
                "repository": "example/demo",
                "pull_request": 1,
                "review": "Fake review for local testing.",
            }
            review_jobs.complete_review_job(job_id, result)

            response = client.get(path, headers=headers)
            assert response.status_code == 200
            assert response.json()["status"] == "completed"
            assert response.json()["result"] == result
            print("Completed result retrieval: PASSED")

            failed_id = review_jobs.create_review_job()
            review_jobs.fail_review_job(
                failed_id,
                "Example safe failure message",
            )

            response = client.get(
                f"/review-jobs/{failed_id}",
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json()["status"] == "failed"
            assert response.json()["error"] == (
                "Example safe failure message"
            )
            print("Failed status retrieval: PASSED")

            response = client.get(
                "/review-jobs/does-not-exist",
                headers=headers,
            )
            assert response.status_code == 404
            print("Unknown job returns 404: PASSED")

            with patch.dict(os.environ, {"DEMO_ACCESS_KEY": ""}):
                response = client.get(path, headers=headers)
                assert response.status_code == 503
                print("Unconfigured authentication rejected: PASSED")

        print("All job-status checks passed.")


if __name__ == "__main__":
    test_review_job_status()