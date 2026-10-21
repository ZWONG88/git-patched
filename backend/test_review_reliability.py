"""Offline regression tests: no credentials, .env loading, or network access."""
import os
import socket
import unittest
from unittest.mock import patch

os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": "us-west-2",
    "AWS_EC2_METADATA_DISABLED": "true", "USE_DYNAMODB": "true",
    "JOBS_TABLE": "pr-guardian-jobs", "DEMO_ACCESS_KEY": "local-test-key-only",
})
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.testclient import TestClient
from moto import mock_aws


def block_network(*args, **kwargs):
    raise AssertionError("Offline test attempted a network connection")


class ReviewReliabilityTests(unittest.TestCase):
    def setUp(self):
        for item in (
            patch("dotenv.load_dotenv", return_value=False),
            patch.object(socket.socket, "connect", block_network),
            patch.object(socket.socket, "connect_ex", block_network),
            patch("socket.create_connection", side_effect=block_network),
            mock_aws(),
        ):
            item.start()
            self.addCleanup(item.stop)
        import review_jobs
        import review_worker
        self.jobs = review_jobs
        self.worker = review_worker
        self.clock = patch.object(review_jobs, "_now", return_value=100000)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.table = boto3.resource("dynamodb").create_table(
            TableName="pr-guardian-jobs", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
        )

    def new_job(self):
        return self.jobs.create_review_job("https://github.com/example/demo/pull/1")

    def test_undelivered_job_reports_failure_without_database_write(self):
        job_id = self.new_job()
        self.now.return_value += self.jobs.QUEUE_SECONDS
        view = self.jobs.get_review_job(job_id)
        self.assertEqual(view["status"], "failed")
        self.assertIn("did not start", view["error_message"])
        stored = self.table.get_item(Key={"job_id": job_id})["Item"]
        self.assertEqual(stored["status"], "queued")
        self.assertFalse(self.jobs.claim_review_job(job_id))

    def test_worker_timeout_is_visible_through_authenticated_status_api(self):
        from main import app
        job_id = self.new_job()
        self.assertTrue(self.jobs.claim_review_job(job_id))
        self.now.return_value += self.jobs.RUN_SECONDS
        with TestClient(app) as client:
            response = client.get(f"/review-jobs/{job_id}", headers={"x-demo-key": "local-test-key-only"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")
        self.assertIn("time limit", response.json()["error"])

    def test_normal_completion_is_not_reclassified_as_timeout(self):
        job_id = self.new_job()
        self.jobs.claim_review_job(job_id)
        self.jobs.complete_review_job(job_id, {"review": "Good review"})
        self.now.return_value += self.jobs.QUEUE_SECONDS + self.jobs.RUN_SECONDS
        self.assertEqual(self.jobs.get_review_job(job_id)["status"], "completed")

    def test_expired_ttl_is_hidden_before_dynamodb_deletes_row(self):
        job_id = self.new_job()
        self.now.return_value += 24 * 3600
        self.assertIsNone(self.jobs.get_review_job(job_id))

    def test_progress_cannot_create_nonexistent_jobs(self):
        with self.assertRaises(ClientError):
            self.jobs.update_review_job("missing", "generating")
        self.assertEqual(self.table.scan()["Count"], 0)

    def test_terminal_result_cannot_be_overwritten(self):
        job_id = self.new_job()
        self.jobs.claim_review_job(job_id)
        result = {"review": "Original result"}
        self.jobs.complete_review_job(job_id, result)
        for change in (
            lambda: self.jobs.update_review_job(job_id, "generating"),
            lambda: self.jobs.fail_review_job(job_id, "Late failure"),
            lambda: self.jobs.complete_review_job(job_id, {"review": "Overwrite"}),
        ):
            with self.assertRaises(ClientError):
                change()
        self.assertEqual(self.jobs.get_review_job(job_id)["review_result"], result)

    def test_late_worker_cannot_complete_after_deadline(self):
        job_id = self.new_job()
        self.jobs.claim_review_job(job_id)
        self.now.return_value += self.jobs.RUN_SECONDS
        with self.assertRaises(ClientError):
            self.jobs.complete_review_job(job_id, {"review": "Too late"})

    def test_unusable_reviewer_results_fail_safely(self):
        for result in (None, {}, {"review": ""}, {"review": "   "}, {"review": 42}):
            with self.subTest(result=result):
                job_id = self.new_job()
                with self.assertLogs("review_worker", level="ERROR"):
                    response = self.worker.process_review_job(job_id, reviewer=lambda *args, **kwargs: result)
                self.assertEqual(response["status"], "failed")
                self.assertNotIn("review_result", self.jobs.get_review_job(job_id))

    def test_reviewer_exception_does_not_leak_into_status_or_logs(self):
        job_id = self.new_job()
        def reviewer(*args, **kwargs):
            raise RuntimeError("private-token-placeholder")
        with self.assertLogs("review_worker", level="ERROR") as logs:
            self.worker.process_review_job(job_id, reviewer=reviewer)
        self.assertNotIn("private-token-placeholder", str(logs.output))
        self.assertNotIn("private-token-placeholder", str(self.jobs.get_review_job(job_id)))

    def test_http_exception_details_are_not_returned_to_client(self):
        job_id = self.new_job()
        def reviewer(*args, **kwargs):
            raise HTTPException(502, "private-upstream-detail")
        self.worker.process_review_job(job_id, reviewer=reviewer)
        self.assertNotIn("private-upstream-detail", str(self.jobs.get_review_job(job_id)))

    def test_unknown_progress_stage_is_ignored(self):
        job_id = self.new_job()
        def reviewer(pr_url, report):
            report("untrusted-stage")
            self.assertEqual(self.jobs.get_review_job(job_id)["stage"], "fetching")
            return {"review": "Sample review"}
        self.assertEqual(self.worker.process_review_job(job_id, reviewer=reviewer)["status"], "completed")

    def test_reviewer_is_never_called_for_expired_job(self):
        job_id = self.new_job()
        self.now.return_value += self.jobs.QUEUE_SECONDS
        def reviewer(*args, **kwargs):
            self.fail("Reviewer should not run")
        with self.assertRaises(ValueError):
            self.worker.process_review_job(job_id, reviewer=reviewer)

    def test_non_ascii_demo_key_returns_unauthorized(self):
        from main import app
        with TestClient(app) as client:
            # UTF-8 bytes emulate a non-ASCII HTTP header without httpx's ASCII encoding restriction.
            response = client.get("/review-jobs/missing", headers={b"x-demo-key": "wrong-🔑".encode("utf-8")})
        self.assertEqual(response.status_code, 401)

    def test_zero_daily_limit_blocks_before_creating_usage_row(self):
        from dynamodb_usage import claim_dynamodb_review
        with patch.dict(os.environ, {"DAILY_REVIEW_LIMIT": "0"}):
            with self.assertRaises(HTTPException) as raised:
                claim_dynamodb_review()
        self.assertEqual(raised.exception.status_code, 429)

    def test_daily_limit_stops_after_exact_number_of_claims(self):
        from dynamodb_usage import claim_dynamodb_review
        table = boto3.resource("dynamodb").create_table(
            TableName="pr-guardian-usage", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "date", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "date", "AttributeType": "S"}],
        )
        with patch.dict(os.environ, {"DAILY_REVIEW_LIMIT": "2", "DYNAMODB_TABLE": "pr-guardian-usage"}):
            claim_dynamodb_review()
            claim_dynamodb_review()
            with self.assertRaises(HTTPException) as raised:
                claim_dynamodb_review()
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(int(table.scan()["Items"][0]["review_count"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
