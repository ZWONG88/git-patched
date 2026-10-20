# PR Guardian: local verification and deployment handoff

## Start the interactive demo

From the project root:

```bash
cd frontend
npm run dev:demo
```

Open the exact Local URL printed by Vite. Confirm the Local simulation banner appears and there is no Demo Access Key input. Enter https://github.com/example/demo/pull/1. The browser simulation makes no network requests to GitHub, AWS, or Gemini. It does not test real backend authentication or AWS delivery; the separate backend tests cover the simulated backend flow.

Use the scenario dropdown before starting a review:

| Scenario | Expected result |
| --- | --- |
| Successful review | Stages advance and a sample review appears in about ten seconds. |
| Review fails | A safe failure message appears after about four seconds; the form is available again. |
| Connection drops once | An error appears with a job ID. Check review status resumes that same job. |
| Submission response is lost | An error appears with the already-created job ID. Check review status retrieves it without creating another job. |
| Review takes longer | Checks pause after twelve seconds while the job continues. Resume until the sample result appears after about thirty seconds total. |

While a job is active, Pause status checks stops polling but does not cancel the background review. Check review status resumes it. Start another review abandons tracking of the old job, not its execution. Refreshing the page clears the browser-only simulations. Access keys are not saved to local storage.

Manual browser checks still required: rapidly double-click Analyze and confirm a single active job; try an invalid URL; pause and resume; verify dropdown and recovery controls at phone width and by keyboard. Automated tests cover API and polling behavior, not browser layout or every React interaction. Browser automation was declined in this session, so the final UI changes have not been visually verified by the agent.

## Repeat automated checks

From the project root:

```bash
cd frontend
npm run lint
npm test
npm run build
```

From the project root, run each backend check separately:

```bash
cd backend
./.venv312/bin/python -B test_review_jobs.py
./.venv312/bin/python -B test_review_worker.py
./.venv312/bin/python -B test_review_job_status.py
./.venv312/bin/python -B test_review_job_submission.py
./.venv312/bin/python -B test_review_reliability.py
```

If recreating a Python environment, install requirements.txt and moto[dynamodb] plus httpx. The test scripts set dummy credentials and run Moto; all except the legacy storage-only script explicitly block network connections. Do not run test_gemini.py as part of offline verification: it may use the real provider. A Starlette/httpx deprecation warning is currently non-fatal.

## Prepare and validate deployment files locally

From the project root:

```bash
./backend/.venv312/bin/python prepare_lambda_package.py
sam validate --lint --template-file template.yaml --region us-west-2
sam build --use-container --template-file template.yaml
```

Keep Docker Desktop running. If SAM cannot locate the Docker connection, set this in that terminal:

```bash
export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
```

Source staging includes only the five application Python modules and requirements.txt. Build and source-staging folders must stay ignored. Dependencies are not yet pinned to a lockfile, so a later rebuild can resolve newer versions. The prior container build and local Lambda health endpoint passed before these reliability updates; repeat the container build to verify this updated package.

The template now references the proposed PRGuardianRuntimeBoundary policy. This is only a local template setting. That customer-managed IAM policy must exist before deployment; its creation requires the account owner's access. It is not required for local simulations or SAM validation/build.

## Timeout behavior and its limits

New jobs include a one-hour queue deadline. A claimed job includes a four-minute run deadline, allowing one minute beyond the template's three-minute Lambda timeout. Reads derive a safe failed status after a deadline, without changing the stored row or requiring another API write permission. Expired 24-hour TTL rows are hidden immediately even if DynamoDB has not removed them yet. Strongly consistent reads reduce stale status after a claim or completion. Progress cannot create phantom jobs or overwrite a terminal result; late worker writes are conditional.

The physical stored row can remain queued/running after an interruption; the status API presents its derived failure. Existing older rows without deadlines do not gain deadlines retroactively. The failure queue retains invocation errors, not application exceptions the worker catches and records itself. Keep code deadlines aligned with the SAM timeout and asynchronous event-age configuration.

There is still no end-to-end exactly-once guarantee for paid provider calls. A submission timeout before the browser receives a job ID can be ambiguous. The frontend does not automatically retry POSTs, and advises against immediate resubmission. Refresh recovery and a client-supplied idempotency key are future improvements.

## Hackathon demonstration: about two minutes

1. Explain the problem: reviewers need a quick first pass over a public pull request.
2. Show the Local simulation banner, then submit the sample URL.
3. Explain queued work, progress polling, and durable job results while stages advance.
4. Show the sample result and clearly state it is simulated, not a live code analysis.
5. Run Connection drops once; demonstrate recovery with the same job ID.
6. Describe the next deployment step: two Lambda functions, DynamoDB jobs/usage, narrowly scoped runtime roles, and secrets kept out of the source package.

## Remaining cloud work

No AWS permissions, secrets, buckets, stacks, or other cloud resources were changed by these local edits.

Still required: owner review/application of deployment access and runtime boundary, creation of the artifact bucket and two secrets, deployment change-set review, checking concurrency quota availability, a deployed API/worker smoke test with one real public PR, Gemini model availability and provider timeout checks, actual IAM checks, production frontend origin/API configuration, and frontend hosting. The local browser simulation is disabled in production builds. Application limits and API throttling are not AWS spending caps. The shared demo key is demo authentication, not per-user accounts or job ownership.
