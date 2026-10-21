"""Run the real PR Guardian API locally with Moto and a fake background reviewer.

Development helper only. Not included by prepare_lambda_package.py.
"""
import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import boto3
from moto import mock_aws

DEMO_KEY = "local-integration-only"
FRONTEND_ORIGIN = "http://localhost:5180"


def _loopback_only(original):
    def guarded(address, *args, **kwargs):
        if not isinstance(address, tuple) or address[0] not in (
            "localhost", "127.0.0.1", "::1",
        ):
            raise RuntimeError("Offline demo blocked an external network connection")
        return original(address, *args, **kwargs)
    return guarded


def _local_dns_only(host, *args, **kwargs):
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Offline demo blocked external DNS lookup")
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


_ORIGINAL_GETADDRINFO = socket.getaddrinfo


@contextmanager
def offline_app(step_delay=1.5):
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SESSION_TOKEN": "testing",
            "AWS_DEFAULT_REGION": "us-west-2",
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_CONFIG_FILE": os.devnull,
            "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "USE_DYNAMODB": "true",
            "JOBS_TABLE": "pr-guardian-jobs",
            "DEMO_ACCESS_KEY": DEMO_KEY,
            "REVIEW_WORKER_FUNCTION_NAME": "offline-fake-worker",
            "FRONTEND_URL": FRONTEND_ORIGIN,
            "GEMINI_API_KEY": "not-a-real-key",
        }))
        for name in list(os.environ):
            if name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE") or name.startswith("AWS_ENDPOINT_URL"):
                os.environ.pop(name)
        stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        stack.enter_context(patch.object(boto3, "DEFAULT_SESSION", None))
        stack.enter_context(patch.object(socket.socket, "connect", _loopback_only(socket.socket.connect)))
        stack.enter_context(patch.object(socket.socket, "connect_ex", _loopback_only(socket.socket.connect_ex)))
        stack.enter_context(patch("socket.getaddrinfo", side_effect=_local_dns_only))
        stack.enter_context(mock_aws())

        # Import only after setting dummy configuration and disabling .env loading.
        import main
        import review_worker

        boto3.resource("dynamodb", region_name="us-west-2").create_table(
            TableName="pr-guardian-jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        def fake_reviewer(pr_url, report=None):
            for stage in ("fetching", "checking", "preparing", "generating", "formatting"):
                if report:
                    report(stage)
                time.sleep(step_delay)
            return {
                "repository": "example/demo",
                "pull_request": 1,
                "review": (
                    "## Local frontend-to-backend check passed\n\n"
                    "The real frontend submitted a job to the real FastAPI endpoint. "
                    "The worker claimed it, saved progress, and stored this result in Moto.\n\n"
                    "**Sample review only.** No GitHub code was fetched and no AWS or Gemini calls were made."
                ),
            }

        pool = stack.enter_context(ThreadPoolExecutor(max_workers=1))

        class FakeLambda:
            def invoke(self, FunctionName, InvocationType, Payload):
                if FunctionName != "offline-fake-worker" or InvocationType != "Event":
                    raise ValueError("Unexpected local invocation")
                event = json.loads(Payload)
                pool.submit(review_worker.process_review_job, event["job_id"], reviewer=fake_reviewer)
                return {"StatusCode": 202}

        client = FakeLambda()
        stack.enter_context(patch.object(main, "get_review_worker_client", return_value=client))
        yield main.app


def run():
    import uvicorn
    print("OFFLINE INTEGRATION DEMO — in-memory Moto data and fake reviewer")
    print(f"Frontend origin: {FRONTEND_ORIGIN}")
    print(f"Dummy demo key: {DEMO_KEY}")
    print("Real .env loading and external network connections are blocked.")
    with offline_app() as app:
        uvicorn.run(app, host="127.0.0.1", port=8010, log_level="info")


if __name__ == "__main__":
    run()
