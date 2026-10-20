
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import './App.css'

function App() {
  const [prUrl, setPrUrl] = useState('')
  const [demoKey, setDemoKey] = useState('')
  const [review, setReview] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function analyzePR() {
    if (!prUrl.trim()) {
      setError('Please enter a GitHub pull request URL.')
      return
    }

    setLoading(true)
    setError('')
    setReview('')

    try {
      
          
const apiUrl =
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

const response = await fetch(
  `${apiUrl}/ai-review?pr_url=${encodeURIComponent(prUrl)}`,
  {
    headers: {
      'x-demo-key': demoKey
    }
  }
)



      const data = await response.json()

      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : 'Something went wrong.'
        )
      }

      setReview(data.review || 'No review was returned.')
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

      <input
        type="url"
        placeholder="https://github.com/owner/repo/pull/123"
        value={prUrl}
        onChange={(event) => setPrUrl(event.target.value)}
      />

      
<input
  type="password"
  placeholder="Enter demo access key"
  value={demoKey}
  onChange={(event) => setDemoKey(event.target.value)}
  autoComplete="off"
/>

      <button onClick={analyzePR} disabled={loading}>
        {loading ? 'Analyzing...' : 'Analyze Pull Request'}
      </button>

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

    </main>
  )
}

export default App
