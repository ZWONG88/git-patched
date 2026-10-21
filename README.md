# GitPatched 🩹

**Catch the bug before the merge.**

GitPatched is a full-stack web application that reviews public GitHub pull requests using Google Gemini. It retrieves proposed code changes, processes reviews in the background, and displays formatted feedback through a React interface.

**Live demo:** https://ubiquitous-gelato-1c226a.netlify.app

A demo access key is required to submit and view reviews.

## Features

- **Public GitHub PR reviews:** Submit a pull request URL for analysis.
- **AI feedback:** Receive suggestions about potential bugs, security concerns, performance, and code quality.
- **Background processing:** Reviews run independently of the initial API request.
- **Progress tracking:** The frontend polls for review status and displays completed results.
- **Connection recovery:** Resume status checks after a temporary connection failure.
- **Demo authentication:** Review endpoints require a shared access key.
- **Daily usage limits:** DynamoDB tracks deployed AI review attempts.
- **Review caching:** Reuse cached feedback when available and the pull request has not changed.
- **Local simulation:** Explore the interface and recovery scenarios without external API calls.

## Tech Stack

### Frontend

- React
- Vite
- JavaScript and CSS
- Netlify hosting

### Backend

- Python
- FastAPI
- Mangum
- GitHub REST API
- Google Gemini API
- SQLite for review caching and local storage

### AWS Infrastructure

- **API Gateway:** Public HTTP API.
- **Lambda:** API handling and background review processing.
- **DynamoDB:** Review jobs and daily usage tracking.
- **Secrets Manager:** Deployment secrets.
- **CloudWatch:** Application logs.
- **SQS:** Destination for failed asynchronous Lambda invocations.
- **S3:** Deployment artifacts.
- **AWS SAM and CloudFormation:** Infrastructure configuration and deployment.

## How It Works

1. A user submits a public GitHub pull request URL and demo access key.
2. The API validates the request and creates a review job in DynamoDB.
3. The API invokes the background review worker.
4. The worker retrieves the pull request's changed files from GitHub.
5. It checks for an available cached review.
6. If a new review is needed, the worker checks the daily usage limit and requests analysis from Gemini.
7. The worker records the result or failure.
8. The frontend polls the API and displays the review.

## Local Frontend Preview

From the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open the address printed by Vite.

To connect the frontend to an API, create `frontend/.env.local`:

```dotenv
VITE_API_URL=https://your-api-base-url
VITE_LOCAL_DEMO=false
```

Restart Vite after changing environment settings.

The API must allow the local frontend's origin for browser requests to work. The deployed demo currently allows its public Netlify origin.

Do not put Gemini credentials or the demo access key in `VITE_*` variables. Vite exposes these variables in the browser bundle.

## Local Simulation

To explore the frontend without calling GitHub, AWS, or Gemini:

```bash
cd frontend
npm install
npm run dev:demo
```

Simulation mode includes sample results and recovery scenarios. It does not perform a real code review.

## Backend Development

Install the backend dependencies using a Python virtual environment:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create `backend/.env` for local development:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
DEMO_ACCESS_KEY=your_private_demo_access_key
DAILY_REVIEW_LIMIT=20
```

Start the development API:

```bash
python -m uvicorn main:app --reload
```

Starting the API alone does not configure the background review worker or reproduce the deployed AWS architecture.

See `LOCAL_READINESS.md` for additional local validation and deployment preparation notes.

## Build the Frontend

```bash
cd frontend
npm run build
```

Vite writes the production website to `frontend/dist`.

The current Netlify deployment uses a manual upload of this folder. Pushing changes to GitHub does not automatically publish them to Netlify.

## AWS Deployment

Infrastructure is defined in `template.yaml`.

Prepare the deployment source and build it using a container:

```bash
python3 prepare_lambda_package.py
sam build --use-container --template-file template.yaml
```

Docker must be running for the container build.

Deployment requires an appropriately authorized AWS identity, an artifact bucket, a runtime permissions boundary, and these parameters:

- `FrontendOrigin`: The frontend origin, without a trailing slash.
- `DemoAccessSecretArn`: The demo access key's Secrets Manager ARN.
- `GeminiSecretArn`: The Gemini API key's Secrets Manager ARN.

Supply the current frontend origin explicitly when deploying. Review the generated CloudFormation change set before executing it.

## API Routes

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/` | Health check |
| POST | `/review-jobs` | Submit a review |
| GET | `/review-jobs/{job_id}` | Retrieve review status and results |

Review submission and retrieval require the `x-demo-key` header.

## Security and Limitations

- Gemini credentials remain on the backend and are not included in the frontend build.
- The shared demo access key is entered by users and sent with authenticated review requests.
- Secret files should never be committed to Git.
- DynamoDB stores deployed review jobs and daily usage counts.
- CORS controls permitted browser origins; it does not replace authentication.
- SQLite review caching is local to each Lambda environment. It is not a shared, durable cloud cache.
- Reloading the page currently loses the frontend's active job tracking.
- Gemini availability, provider quotas, and GitHub rate limits can prevent reviews from completing.
- The daily review limit is an application control, not a billing cap.
- AI feedback can contain mistakes and requires human review.
- This demo analyzes public pull requests. It does not automatically modify code, post GitHub comments, or merge pull requests.

## Project Status

Deployed and tested as a public demo.

The Netlify frontend, AWS API, background worker, DynamoDB job tracking, demo authentication, and real Gemini review flow have been exercised end to end.

Local simulation and recovery scenarios have also been tested.

Further production work would include individual user authentication, stronger abuse protection, durable shared caching, automated deployment, and broader operational monitoring.