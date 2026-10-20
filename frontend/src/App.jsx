import { useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  getReviewStatus,
  localDemo,
  submitReview,
} from './reviewApi'
import './App.css'

const stages = [
  { id: 'fetching', label: 'Fetching GitHub pull request' },
  { id: 'checking', label: 'Checking review cache' },
  { id: 'preparing', label: 'Preparing code changes' },
  { id: 'generating', label: 'Generating AI code review' },
  { id: 'formatting', label: 'Preparing review results' },
]

const pause = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds))

function App() {
  const [prUrl, setPrUrl] = useState('')
  const [demoKey, setDemoKey] = useState('')
  const [review, setReview] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [currentStage, setCurrentStage] = useState('')
  const [completedStages, setCompletedStages] = useState([])
  const [activeJob, setActiveJob] = useState(null)
  const busy = useRef(false)

  async function analyzePR() {
    if (busy.current) return

    if (!activeJob) {
      const validUrl = /^https:\/\/github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+\/pull\/[1-9][0-9]*\/?$/

      if (!validUrl.test(prUrl.trim())) {
        setError('Please enter a valid GitHub pull request URL.')
        return
      }

      if (!localDemo && !demoKey) {
        setError('Please enter your demo access key.')
        return
      }
    }

    busy.current = true
    setLoading(true)
    setError('')
    setReview('')

    let job = activeJob

    try {
      if (!job) {
        setCurrentStage('fetching')
        setCompletedStages([])

        try {
          const submitted = await submitReview(prUrl.trim(), demoKey)

          if (!submitted.job_id) {
            throw new Error('Submission returned no job ID.')
          }

          job = { id: submitted.job_id, key: demoKey }
          setActiveJob(job)
        } catch (submissionError) {
          if (submissionError.jobId) {
            setActiveJob({
              id: submissionError.jobId,
              key: demoKey,
            })
          }
          throw submissionError
        }
      }

      const deadline = Date.now() + 5 * 60 * 1000

      while (Date.now() < deadline) {
        const status = await getReviewStatus(job.id, job.key)

        if (status.status === 'failed') {
          setActiveJob(null)
          throw new Error(status.error || 'The review failed.')
        }

        if (status.status === 'completed') {
          const text = status.result?.review

          if (typeof text !== 'string' || !text.trim()) {
            throw new Error('The completed job returned no review text.')
          }

          setReview(text)
          setCurrentStage('complete')
          setCompletedStages(stages.map((stage) => stage.id))
          setActiveJob(null)
          return
        }

        if (!['queued', 'running'].includes(status.status)) {
          throw new Error('The server returned an unexpected job status.')
        }

        const stage =
          status.stage === 'cached' ? 'formatting' : status.stage
        const index = stages.findIndex((item) => item.id === stage)

        if (index >= 0) {
          setCurrentStage(stage)
          setCompletedStages(stages.slice(0, index).map((item) => item.id))
        }

        await pause(2000)
      }

      throw new Error(
        'The review is taking longer than expected. Click Check review status to keep checking the same job.',
      )
    } catch (err) {
      setError(
        err.name === 'TimeoutError'
          ? 'The request timed out. If a job ID is shown, check its status.'
          : err.message || 'Could not connect to the backend.',
      )
    } finally {
      busy.current = false
      setLoading(false)
    }
  }

  return (
    <main>
      <h1>PR Guardian 🛡️</h1>
      <p>Your AI-powered GitHub code reviewer</p>

      {localDemo && (
        <p role="status">
          🧪 Local simulation — sample results, no external calls.
        </p>
      )}

      <label className="field-label" htmlFor="pr-url">
        GitHub Pull Request URL
      </label>
      <input
        id="pr-url"
        type="url"
        placeholder="https://github.com/owner/repo/pull/123"
        value={prUrl}
        onChange={(event) => setPrUrl(event.target.value)}
        disabled={loading || Boolean(activeJob)}
      />

      <p className="input-hint">
        {localDemo
          ? 'Use a sample GitHub URL to try the review flow.'
          : 'Paste a public GitHub pull request URL.'}
      </p>

      {!localDemo && (
        <>
          <label className="field-label" htmlFor="demo-key">
            Demo Access Key
          </label>
          <input
            id="demo-key"
            type="password"
            placeholder="Enter demo access key"
            value={demoKey}
            onChange={(event) => setDemoKey(event.target.value)}
            autoComplete="off"
            disabled={loading || Boolean(activeJob)}
          />
        </>
      )}

      <button onClick={analyzePR} disabled={loading}>
        {loading ? (
          <span className="button-loading">
            <span className="loading-spinner" aria-hidden="true" />
            Checking Review Progress...
          </span>
        ) : activeJob ? (
          'Check review status'
        ) : (
          'Analyze Pull Request'
        )}
      </button>

      {activeJob && <p className="input-hint">Job ID: {activeJob.id}</p>}

      {loading && (
        <div className="review-stages" role="status" aria-live="polite">
          <h3>Review in progress</h3>
          {stages.map((stage) => {
            const completed = completedStages.includes(stage.id)
            const active = currentStage === stage.id

            return (
              <div
                key={stage.id}
                className={`review-stage ${completed ? 'stage-complete' : ''} ${active ? 'stage-active' : ''}`}
              >
                <span className="stage-icon" aria-hidden="true">
                  {completed ? '✓' : active ? '◉' : '○'}
                </span>
                <span>{stage.label}</span>
                {active && <span className="stage-status">In progress</span>}
              </div>
            )
          })}
          <p className="review-progress-caption">
            {localDemo
              ? 'This simulation takes about ten seconds.'
              : 'Checking job status every two seconds.'}
          </p>
        </div>
      )}

      {error && (
        <p role="alert" style={{ color: '#f87171' }}>
          {error}
        </p>
      )}

      {review && (
        <section className="review-results">
          <h2>{localDemo ? '🧪 Sample Review' : '🛡️ AI Code Review'}</h2>
          <div className="markdown-content">
            <ReactMarkdown>{review}</ReactMarkdown>
          </div>
        </section>
      )}

      <footer className="app-footer">
        <p>Powered by React, FastAPI, GitHub API &amp; Google Gemini</p>
        <p className="footer-subtitle">
          AI-assisted reviews are suggestions, not a substitute for human review.
        </p>
      </footer>
    </main>
  )
}

export default App