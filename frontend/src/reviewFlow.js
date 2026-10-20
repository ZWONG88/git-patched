export function wait(milliseconds, signal) {
  signal?.throwIfAborted()
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer)
      reject(signal.reason)
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, milliseconds)
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

export async function pollReview({
  jobId, key, getStatus, onProgress = () => {}, signal,
  timeout = 300000, interval = 2000, now = () => Date.now(), sleep = wait,
}) {
  const deadline = now() + timeout
  while (now() < deadline) {
    signal?.throwIfAborted()
    const status = await getStatus(jobId, key, { signal })
    signal?.throwIfAborted()
    if (status.status === 'failed') {
      const error = new Error(status.error || 'The review failed.')
      error.terminal = true
      throw error
    }
    if (status.status === 'completed') {
      const text = status.result?.review
      if (typeof text !== 'string' || !text.trim()) {
        const error = new Error('The completed job returned no usable review. Start another review.')
        error.terminal = true
        throw error
      }
      return text
    }
    if (!['queued', 'running'].includes(status.status)) {
      throw new Error('The server returned an unexpected job status. You can check again.')
    }
    onProgress(status)
    await sleep(Math.min(interval, Math.max(0, deadline - now())), signal)
  }
  throw new Error('Still waiting. Choose Check review status to continue checking the same job.')
}
