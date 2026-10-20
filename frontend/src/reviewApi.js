export const localDemo =
  import.meta.env.DEV &&
  import.meta.env.VITE_LOCAL_DEMO === 'true'

const apiUrl = (
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')

const demoJobs = new Map()

async function request(path, key, options = {}) {
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: {
      ...options.headers,
      'x-demo-key': key,
    },
    signal: AbortSignal.timeout(15000),
  })

  const data = await response.json()

  if (!response.ok) {
    const detail = data.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || `Request failed (${response.status}).`

    const error = new Error(message)
    error.jobId = detail?.job_id
    throw error
  }

  return data
}

export async function submitReview(prUrl, key) {
  if (localDemo) {
    const jobId = crypto.randomUUID()
    demoJobs.set(jobId, Date.now())
    return { job_id: jobId, status: 'accepted' }
  }

  return request('/review-jobs', key, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pr_url: prUrl }),
  })
}

export async function getReviewStatus(jobId, key) {
  if (localDemo) {
    const started = demoJobs.get(jobId)

    if (!started) {
      throw new Error('Local simulation expired. Start a new review.')
    }

    const elapsed = Date.now() - started
    const stages = [
      'fetching',
      'checking',
      'preparing',
      'generating',
      'formatting',
    ]

    if (elapsed < 10000) {
      return {
        job_id: jobId,
        status: elapsed < 2000 ? 'queued' : 'running',
        stage: stages[Math.min(4, Math.floor(elapsed / 2000))],
      }
    }

    return {
      job_id: jobId,
      status: 'completed',
      stage: 'complete',
      result: {
        review: [
          '## Local simulation completed',
          '',
          'Submission, progress polling, and result display worked.',
          '',
          '**This is sample text.** No GitHub code was fetched,',
          'and no AWS or Gemini calls were made.',
        ].join('\n'),
      },
    }
  }

  return request(`/review-jobs/${encodeURIComponent(jobId)}`, key)
}