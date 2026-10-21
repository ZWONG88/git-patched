import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  demoScenarios,
  getReviewStatus,
  localDemo,
  submitReview,
} from './reviewApi'
import { pollReview } from './reviewFlow'
import './App.css'

const stages = [
  { id: 'fetching', label: 'Fetching GitHub pull request' },
  { id: 'checking', label: 'Checking review cache' },
  { id: 'preparing', label: 'Preparing code changes' },
  { id: 'generating', label: 'Generating AI code review' },
  { id: 'formatting', label: 'Preparing review results' },
]

function App() {
  const [prUrl, setPrUrl] = useState('')
  const [demoKey, setDemoKey] = useState('')
  const [review, setReview] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [currentStage, setCurrentStage] = useState('')
  const [completedStages, setCompletedStages] = useState([])
  const [activeJob, setActiveJob] = useState(null)
  const [scenario, setScenario] = useState('success')
  const busy = useRef(false)
  const controller = useRef(null)

  useEffect(() => () => controller.current?.abort(), [])

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

    const attempt = new AbortController()
    controller.current = attempt
    let job = activeJob

    try {
      if (!job) {
        setCurrentStage('fetching')
        setCompletedStages([])
        try {
          const submitted = await submitReview(prUrl.trim(), demoKey, {
            scenario, signal: attempt.signal,
          })
          if (typeof submitted.job_id !== 'string' || !submitted.job_id) {
            throw new Error('Submission returned no job ID. Check with the operator before resubmitting.')
          }
          job = { id: submitted.job_id }
          setActiveJob(job)
        } catch (submissionError) {
          if (submissionError.jobId) {
            setActiveJob({ id: submissionError.jobId })
          }
          throw submissionError
        }
      }
      const text = await pollReview({
        jobId: job.id,
        key: demoKey,
        getStatus: getReviewStatus,
        signal: attempt.signal,
        timeout: localDemo && scenario === 'slow' ? 12000 : 300000,
        onProgress: (status) => {
          const stage = status.stage === 'cached' ? 'formatting' : status.stage
          const index = stages.findIndex((item) => item.id === stage)
          if (index >= 0) {
            setCurrentStage(stage)
            setCompletedStages(stages.slice(0, index).map((item) => item.id))
          }
        },
      })
      setReview(text)
      setCurrentStage('complete')
      setCompletedStages(stages.map((stage) => stage.id))
      setActiveJob(null)
    } catch (err) {
      if (attempt.signal.aborted) return
      if (err.terminal) setActiveJob(null)
      setError(
        err.name === 'TimeoutError'
          ? 'The request timed out. Check the existing job if its ID is shown. If no ID arrived, submission may still have succeeded; avoid immediately submitting it again.'
          : err.message || 'Connection lost. Check the existing job if its ID is shown.',
      )
    } finally {
      busy.current = false
      // The controller is cleared on pause; an unmounted component is not updated.
      if (!attempt.signal.aborted || controller.current === null) {
        setLoading(false)
      }
    }
  }

  function pauseChecking() {
    controller.current?.abort()
    controller.current = null
    setError('Status checks paused. The background job may continue. Choose Check review status to resume.')
  }

  function startAnotherReview() {
    setActiveJob(null)
    setError('')
    setReview('')
    setCurrentStage('')
    setCompletedStages([])
  }

  return (
    <main>
      <h1>
        GitPatched{" "}
       <svg
          width="1em"
          height="1em"
          viewBox="0 0 48 48"
          fill="none"
          aria-hidden="true"
          style={{ verticalAlign: "-0.15em" }}
        >
          <g transform="rotate(-45 24 24)">
            <rect
              x="5" y="15" width="38" height="18" rx="7"
              stroke="#a5b4fc" strokeWidth="2.5"
              fill="#6366f1" fillOpacity="0.15"
            />
            <rect
              x="19" y="18" width="10" height="12" rx="2"
              stroke="#a5b4fc" strokeWidth="2"
            />
            <g fill="#a5b4fc">
              <circle cx="12" cy="21" r="1.2" />
              <circle cx="12" cy="27" r="1.2" />
              <circle cx="36" cy="21" r="1.2" />
              <circle cx="36" cy="27" r="1.2" />
            </g>
          </g>
        </svg>
      </h1>
      <p>Catch the bug before the merge.</p>

      {localDemo && (
        <div className="simulation-panel">
          <p role="status">🧪 Local simulation — sample results, no external calls.</p>
          <label className="field-label" htmlFor="scenario">Try a scenario</label>
          <select id="scenario" value={scenario}
            onChange={(event) => setScenario(event.target.value)}
            disabled={loading || Boolean(activeJob)}>
            {demoScenarios.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
          <p className="input-hint">Simulations are held in memory and reset when you reload this page.</p>
        </div>
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
            disabled={loading}
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

      {activeJob && <p className="input-hint job-id">Job ID: {activeJob.id}</p>}

      {loading && activeJob && (
        <button className="secondary-button" onClick={pauseChecking}>Pause status checks</button>
      )}
      {!loading && activeJob && (
        <div className="recovery-options">
          <p className="input-hint">Checking status reuses this job. Starting another leaves the existing job running.</p>
          <button className="secondary-button" onClick={startAnotherReview}>Start another review</button>
        </div>
      )}

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
              ? scenario === 'slow' ? 'This simulation takes about thirty seconds; status checks pause sooner so you can try resuming.' : 'This simulation takes about ten seconds.'
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
