
# PR Guardian

AI-Powered GitHub Pull Request Reviewer

PR Guardian is a full-stack web application that analyzes GitHub pull requests using Google's Gemini AI. It helps developers understand proposed code changes, identify potential issues, and receive actionable review feedback.

## Features

- **GitHub Integration:** Analyze public GitHub pull requests by URL.
- **AI-Powered Reviews:** Generate code review feedback using Google Gemini.
- **Review Caching:** Reuse previously generated reviews when the pull request has not changed.
- **Demo Authentication:** Restrict AI review requests using an access key.
- **Daily Usage Limits:** Track and limit new AI review attempts.
- **Interactive Web Interface:** View formatted AI feedback through a React application.

## Tech Stack

**Frontend**
- React
- Vite
- JavaScript
- CSS

**Backend**
- Python
- FastAPI
- GitHub REST API
- Google Gemini API
- SQLite

## How It Works

1. The user enters a public GitHub pull request URL.
2. The FastAPI backend retrieves the pull request's changed files.
3. The backend checks whether a cached review is available.
4. If needed, Gemini analyzes the code changes.
5. The generated feedback is displayed in the React interface.

## Run Locally

### Backend

Install the dependencies listed in `backend/requirements.txt`.

Create a `backend/.env` file with the following settings:

```env
GEMINI_API_KEY=your_gemini_api_key
DEMO_ACCESS_KEY=your_private_demo_password
DAILY_REVIEW_LIMIT=20
```

Start the API from the `backend` directory:

```bash
python -m uvicorn main:app --reload
```

### Frontend

From the `frontend` directory:

```bash
npm install
npm run dev
```

Open the local URL printed by Vite.

## Project Status

Local development and testing are underway. Public deployment and production hardening are in progress.

## Security Notes

API credentials are stored in server-side environment variables rather than frontend source code.

The application includes demo authentication, review caching, and a local daily usage counter. Production deployment requires persistent usage storage, additional request protection, and appropriate API provider quota controls.
