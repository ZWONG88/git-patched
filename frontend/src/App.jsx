
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import './App.css'

function App() {
  const [prUrl, setPrUrl] = useState('')
  const [demoKey, setDemoKey] = useState('')
  const [review, setReview] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [currentStage, setCurrentStage] = useState('')
  const [completedStages, setCompletedStages] = useState([])

  const stages = [
    { id: 'fetching', label: 'Fetching GitHub pull request' },
    { id: 'checking', label: 'Checking review cache' },
    { id: 'preparing', label: 'Preparing code changes' },
    { id: 'generating', label: 'Generating AI code review' },
    { id: 'formatting', label: 'Preparing review results' },
  ]

  async function analyzePR() {
    if (!prUrl.trim()) {
      setError('Please enter a GitHub pull request URL.')
      return
    }

    setLoading(true)
    setError('')
    setReview('')
    setCurrentStage('fetching')
    setCompletedStages([])
    try {
      
          
const apiUrl =
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

const response = await fetch(
  `${apiUrl}/ai-review-stream?pr_url=${encodeURIComponent(prUrl)}`,
  {
    headers: {
      'x-demo-key': demoKey
    }
  }
)



      
if (!response.ok) {
  let message = 'Could not start the review.'
  try {
    const errorData = await response.json()
    message = errorData.detail || message
  } catch {
    // Keep the default message.
  }
  throw new Error(message)
}

if (!response.body) {
  throw new Error('Streaming is not supported by this browser.')
}

const reader = response.body.getReader()
const decoder = new TextDecoder()
let buffer = ''
let receivedResult = false

while (true) {
  const { value, done } = await reader.read()
  if (done) break

  buffer += decoder.decode(value, { stream: true })

  const lines = buffer.split('\n')
  buffer = lines.pop() || ''

  for (const line of lines) {
    if (!line.trim()) continue

    const event = JSON.parse(line)

    if (event.type === 'progress') {
      const stageIndex = stages.findIndex(
        (stage) => stage.id === event.stage
      )

      if (stageIndex >= 0) {
        setCurrentStage(event.stage)
        setCompletedStages(
          stages.slice(0, stageIndex).map((stage) => stage.id)
        )
      }

      if (event.stage === 'cached') {
        setCurrentStage('formatting')
        setCompletedStages(['fetching', 'checking'])
      }
    }

    if (event.type === 'result') {
      receivedResult = true
      setCompletedStages(stages.map((stage) => stage.id))
      setCurrentStage('complete')
      setReview(event.data.review || 'No review was returned.')
    }

    if (event.type === 'error') {
      throw new Error(event.message || 'Review failed.')
    }
  }
}

if (!receivedResult) {
  throw new Error('The review connection ended unexpectedly.')
}

    } catch (err) {
      setError(err.message || 'Could not connect to the backend.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <h1>PR Guardian 🛡️</h1>
      <p>Your AI-powered GitHub code reviewer</p>

      <label className="field-label" htmlFor="pr-url">
        GitHub Pull Request URL
      </label>

      <input
        type="url"
        placeholder="https://github.com/owner/repo/pull/123"
        value={prUrl}
        onChange={(event) => setPrUrl(event.target.value)}
      />
      <p className="input-hint">
        Paste a public GitHub pull request URL to receive an AI-powered code review.
      </p>

<label className="field-label" htmlFor="demo-key">
  Demo Access Key
</label>

<input
  type="password"
  placeholder="Enter demo access key"
  value={demoKey}
  onChange={(event) => setDemoKey(event.target.value)}
  autoComplete="off"
/>

      <button onClick={analyzePR} disabled={loading}>
        
        {loading ? (
          <span className="button-loading">
            <span className="loading-spinner" aria-hidden="true"></span>
            Analyzing Pull Request...
          </span>
        ) : (
          'Analyze Pull Request'
        )}

      </button>



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
      Gemini analysis time varies depending on the pull request.
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
    <h2>🛡️ AI Code Review</h2>

    <p className="review-disclaimer">
      AI-generated suggestions. Verify findings
      before making changes to your code.
    </p>

    <div className="markdown-content">
      <ReactMarkdown>{review}</ReactMarkdown>
    


    </div>
  </section>
)}
<footer className="app-footer">
  <p>Powered by React, FastAPI, GitHub API &amp; Google Gemini</p>
  <p className="footer-subtitle">
    AI-assisted reviews are suggestions, not a substitute for human code review.
  </p>
</footer>
    </main>
  )
}

export default App
