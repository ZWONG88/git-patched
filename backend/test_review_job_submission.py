import json
import os
import socket
from unittest.mock import Mock, patch

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-west-2"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["USE_DYNAMODB"] = "true"
os.environ["JOBS_TABLE"] = "pr-guardian-jobs"
os.environ["DEMO_ACCESS_KEY"] = "local-test-key-only"
os.environ["REVIEW_WORKER_FUNCTION_NAME"] = "fake-review-worker"

import boto3
from fastapi.testclient import TestClient
from moto import mock_aws


def block_network(*args, **kwargs):
    raise AssertionError("This test must not make network calls.")


def test_review_job_submission():
    with (
        patch("dotenv.load_dotenv", return_value=False),
        patch.object(socket.socket, "connect", block_network),
        patch.object(socket.socket, "connect_ex", block_network),
        patch("socket.create_connection", side_effect=block_network),
        mock_aws(),
    ):
        import main
        import review_jobs

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

        headers = {"x-demo-key": "local-test-key-only"}
        body = {
            "pr_url": "https://github.com/example/demo/pull/1",
        }

        fake_lambda = Mock()

        def fake_invoke(**kwargs):
            assert kwargs["FunctionName"] == "fake-review-worker"
            assert kwargs["InvocationType"] == "Event"

            event = json.loads(kwargs["Payload"])
            assert set(event) == {"job_id"}

            # The URL must already be saved before invocation.
            job = review_jobs.get_review_job(event["job_id"])
            assert job["status"] == "queued"
            assert job["pr_url"] == body["pr_url"]

            return {"StatusCode": 202}

        fake_lambda.invoke.side_effect = fake_invoke

        with (
            patch.object(
                main,
                "get_review_worker_client",
                return_value=fake_lambda,
            ),
            TestClient(main.app) as client,
        ):
            response = client.post("/review-jobs", json=body)
            assert response.status_code == 401
            assert table.scan()["Count"] == 0
            fake_lambda.invoke.assert_not_called()
            print("Missing key rejected without creating a job: PASSED")

            response = client.post(
                "/review-jobs",
                json=body,
                headers={"x-demo-key": "incorrect-key"},
            )
            assert response.status_code == 401
            assert table.scan()["Count"] == 0
            fake_lambda.invoke.assert_not_called()
            print("Incorrect key rejected: PASSED")

            response = client.post(
                "/review-jobs",
                json={"pr_url": "https://example.com/pull/1"},
                headers=headers,
            )
            assert response.status_code == 400
            assert table.scan()["Count"] == 0
            fake_lambda.invoke.assert_not_called()
            print("Invalid URL rejected: PASSED")

            response = client.post(
                "/review-jobs",
                json={},
                headers=headers,
            )
            assert response.status_code == 422
            assert table.scan()["Count"] == 0
            fake_lambda.invoke.assert_not_called()
            print("Missing URL rejected: PASSED")

            with patch.dict(
                os.environ,
                {"REVIEW_WORKER_FUNCTION_NAME": ""},
            ):
                response = client.post(
                    "/review-jobs",
                    json=body,
                    headers=headers,
                )

            assert response.status_code == 503
            assert table.scan()["Count"] == 0
            fake_lambda.invoke.assert_not_called()
            print("Missing worker configuration rejected: PASSED")

            response = client.post(
                "/review-jobs",
                json=body,
                headers=headers,
            )
            assert response.status_code == 202

            data = response.json()
            assert data["status"] == "accepted"
            job_id = data["job_id"]
            fake_lambda.invoke.assert_called_once()
            print("Job saved and background invocation requested: PASSED")

            response = client.get(
                f"/review-jobs/{job_id}",
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json()["status"] == "queued"
            print("Submitted job can be checked: PASSED")
            import review_worker

            expected_result = {
                "repository": "example/demo",
                "pull_request": 1,
                "review": "Complete local flow: fake review succeeded.",
            }
            reviewer_calls = []

            def fake_reviewer(pr_url, report=None):
                reviewer_calls.append(pr_url)
                assert pr_url == body["pr_url"]

                report("generating")

                progress = client.get(
                    f"/review-jobs/{job_id}",
                    headers=headers,
                )
                assert progress.status_code == 200
                assert progress.json()["status"] == "running"
                assert progress.json()["stage"] == "generating"
                print("Running progress available through API: PASSED")

                report("formatting")
                return expected_result

            # Use the exact payload produced by the submission endpoint.
            invocation = fake_lambda.invoke.call_args.kwargs
            worker_event = json.loads(invocation["Payload"])
            assert worker_event == {"job_id": job_id}

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
                worker_response = review_worker.handler(
                    worker_event,
                    None,
                )

            assert worker_response == {
                "job_id": job_id,
                "status": "completed",
            }
            assert reviewer_calls == [body["pr_url"]]
            print("Submitted event processed by worker: PASSED")

            response = client.get(
                f"/review-jobs/{job_id}",
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json() == {
                "job_id": job_id,
                "status": "completed",
                "stage": "complete",
                "result": expected_result,
            }
            print("Completed review retrieved through API: PASSED")

            fake_lambda.invoke.side_effect = RuntimeError(
                "Internal detail that must not reach the client"
            )

            response = client.post(
                "/review-jobs",
                json=body,
                headers=headers,
            )
            assert response.status_code == 503
            assert "Internal detail" not in response.text

            uncertain_id = response.json()["detail"]["job_id"]
            assert review_jobs.get_review_job(uncertain_id) is not None
            print("Invocation failure returns a safe message and job ID: PASSED")

        print("All submission checks passed.")


if __name__ == "__main__":
    test_review_job_submission()