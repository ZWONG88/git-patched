export const localDemo = Boolean(
  import.meta.env?.DEV && import.meta.env?.VITE_LOCAL_DEMO === 'true',
)

export const demoScenarios = [
  { id: 'success', label: 'Successful review' },
  { id: 'failure', label: 'Review fails' },
  { id: 'disconnect', label: 'Connection drops once' },
  { id: 'submission-unknown', label: 'Submission response is lost' },
  { id: 'slow', label: 'Review takes longer' },
]

// Dependency injection lets tests verify the real request contract without a server.
export function createReviewApi({
  demo = false,
  baseUrl = 'http://127.0.0.1:8000',
  fetchImpl = (...args) => fetch(...args),
  now = () => Date.now(),
  makeId = () => crypto.randomUUID(),
  requestTimeout = 15000,
} = {}) {
  const jobs = new Map()
  const origin = baseUrl.replace(/\/+$/, '')

  async function request(path, key, options = {}) {
    const timeout = AbortSignal.timeout(requestTimeout)
    const signal = options.signal
      ? AbortSignal.any([options.signal, timeout])
      : timeout
    const response = await fetchImpl(`${origin}${path}`, {
      ...options,
      headers: { ...options.headers, 'x-demo-key': key },
      signal,
    })
    let data
    try {
      data = await response.json()
    } catch {
      throw new Error(`The server returned an unreadable response (${response.status}).`)
    }
    if (!response.ok) {
      const detail = data?.detail
      const error = new Error(
        typeof detail === 'string'
          ? detail
          : typeof detail?.message === 'string'
            ? detail.message
            : `Request failed (${response.status}).`,
      )
      error.status = response.status
      error.jobId = typeof detail?.job_id === 'string' ? detail.job_id : undefined
      throw error
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      throw new Error('The server returned an unexpected response.')
    }
    return data
  }

  async function submitReview(prUrl, key, { scenario = 'success', signal } = {}) {
    signal?.throwIfAborted()
    if (!demo) {
      return request('/review-jobs', key, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pr_url: prUrl }),
        signal,
      })
    }
    if (!demoScenarios.some((item) => item.id === scenario)) {
      throw new Error('Choose a local simulation scenario.')
    }
    const jobId = makeId()
    jobs.set(jobId, { started: now(), scenario, disconnected: false })
    // Keep only a small number of browser-only simulations in memory.
    if (jobs.size > 50) jobs.delete(jobs.keys().next().value)
    if (scenario === 'submission-unknown') {
      const error = new Error('Submission response was lost. Check the existing job status.')
      error.jobId = jobId
      throw error
    }
    return { job_id: jobId, status: 'accepted' }
  }

  async function getReviewStatus(jobId, key, { signal } = {}) {
    signal?.throwIfAborted()
    if (!demo) {
      return request(`/review-jobs/${encodeURIComponent(jobId)}`, key, { signal })
    }
    const job = jobs.get(jobId)
    if (!job) throw new Error('Local simulation expired. Choose Start another review.')
    const elapsed = now() - job.started
    if (job.scenario === 'disconnect' && elapsed >= 2000 && !job.disconnected) {
      job.disconnected = true
      throw new Error('Simulated connection loss. Check review status to resume this job.')
    }
    if (job.scenario === 'failure' && elapsed >= 4000) {
      return { job_id: jobId, status: 'failed', stage: 'failed', error: 'Simulated review failure. You can try another review.' }
    }
    const duration = job.scenario === 'slow' ? 30000 : 10000
    if (elapsed < duration) {
      const stages = ['fetching', 'checking', 'preparing', 'generating', 'formatting']
      return {
        job_id: jobId,
        status: elapsed < 2000 ? 'queued' : 'running',
        stage: stages[Math.min(4, Math.floor(elapsed / (duration / 5)))],
      }
    }
    return {
      job_id: jobId, status: 'completed', stage: 'complete',
      result: { review: '## Local simulation completed\n\nSubmission, progress polling, and result display worked.\n\n**Sample text only.** No GitHub, AWS, or Gemini calls were made.' },
    }
  }
  return { submitReview, getReviewStatus }
}

const api = createReviewApi({
  demo: localDemo,
  baseUrl: import.meta.env?.VITE_API_URL || 'http://127.0.0.1:8000',
})
export const submitReview = api.submitReview
export const getReviewStatus = api.getReviewStatus
