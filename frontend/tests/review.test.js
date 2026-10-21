import test from 'node:test'
import assert from 'node:assert/strict'
import { createReviewApi, localDemo } from '../src/reviewApi.js'
import { pollReview, wait } from '../src/reviewFlow.js'

const url = 'https://github.com/example/demo/pull/1'
function simulation() {
  let clock = 0
  let ids = 0
  const api = createReviewApi({
    demo: true, now: () => clock, makeId: () => `job-${++ids}`,
    fetchImpl: () => { throw new Error('Simulation attempted a network call') },
  })
  return { ...api, advance: (ms) => { clock += ms } }
}

test('simulation is off unless explicitly enabled by Vite development settings', () => {
  assert.equal(localDemo, false)
})

test('success progresses from queued to running and completed without fetching', async () => {
  const api = simulation()
  const { job_id: id } = await api.submitReview(url, '')
  assert.equal((await api.getReviewStatus(id)).status, 'queued')
  api.advance(6000)
  assert.equal((await api.getReviewStatus(id)).stage, 'generating')
  api.advance(4000)
  assert.match((await api.getReviewStatus(id)).result.review, /Sample text only/)
})

test('failure is terminal with a useful message', async () => {
  const api = simulation()
  const { job_id: id } = await api.submitReview(url, '', { scenario: 'failure' })
  api.advance(4000)
  const status = await api.getReviewStatus(id)
  assert.equal(status.status, 'failed')
  assert.match(status.error, /Simulated review failure/)
})

test('connection loss happens once and the same job can finish', async () => {
  const api = simulation()
  const { job_id: id } = await api.submitReview(url, '', { scenario: 'disconnect' })
  api.advance(2000)
  await assert.rejects(api.getReviewStatus(id), /connection loss/)
  assert.equal((await api.getReviewStatus(id)).status, 'running')
  api.advance(8000)
  assert.equal((await api.getReviewStatus(id)).status, 'completed')
})

test('uncertain submission retains a usable existing job ID', async () => {
  const api = simulation()
  let id
  await assert.rejects(api.submitReview(url, '', { scenario: 'submission-unknown' }), (error) => {
    id = error.jobId
    return Boolean(id)
  })
  api.advance(10000)
  assert.equal((await api.getReviewStatus(id)).status, 'completed')
})

test('real mode sends authenticated JSON and encodes the status path', async () => {
  const calls = []
  const api = createReviewApi({ baseUrl: 'https://api.example/', fetchImpl: async (...args) => {
    calls.push(args)
    return new Response(JSON.stringify({ job_id: 'one', status: 'queued' }))
  } })
  await api.submitReview(url, 'dummy-key')
  assert.equal(calls[0][0], 'https://api.example/review-jobs')
  assert.equal(calls[0][1].method, 'POST')
  assert.equal(calls[0][1].headers['x-demo-key'], 'dummy-key')
  assert.deepEqual(JSON.parse(calls[0][1].body), { pr_url: url })
  await api.getReviewStatus('a/b', 'dummy-key')
  assert.equal(calls[1][0], 'https://api.example/review-jobs/a%2Fb')
})

test('real API preserves structured submission error and job ID', async () => {
  const api = createReviewApi({ fetchImpl: async () => new Response(JSON.stringify({
    detail: { message: 'Check existing job', job_id: 'already-created' },
  }), { status: 503 }) })
  await assert.rejects(api.submitReview(url, 'dummy'), (error) =>
    error.message === 'Check existing job' && error.jobId === 'already-created')
})

test('non-JSON and validation responses produce readable errors', async () => {
  const html = createReviewApi({ fetchImpl: async () => new Response('<html>Error</html>', { status: 502 }) })
  await assert.rejects(html.getReviewStatus('id', 'dummy'), /unreadable response \(502\)/)
  const validation = createReviewApi({ fetchImpl: async () => new Response(JSON.stringify({ detail: [{ msg: 'Missing' }] }), { status: 422 }) })
  await assert.rejects(validation.submitReview(url, 'dummy'), /Request failed \(422\)/)
})

test('polling stops at deadline and resumes the same job without submission', async () => {
  const api = simulation()
  const { job_id: id } = await api.submitReview(url, '', { scenario: 'slow' })
  let clock = 0
  const options = {
    jobId: id, key: '', getStatus: api.getReviewStatus,
    timeout: 12000, now: () => clock,
    sleep: async (ms) => { clock += ms; api.advance(ms) },
  }
  await assert.rejects(pollReview(options), /Still waiting/)
  await assert.rejects(pollReview(options), /Still waiting/)
  assert.match(await pollReview(options), /Local simulation completed/)
})

test('polling marks failures and unusable results terminal', async () => {
  for (const status of [
    { status: 'failed', error: 'Safe failure' },
    { status: 'completed', result: { review: '   ' } },
  ]) {
    await assert.rejects(pollReview({ jobId: 'id', getStatus: async () => status }), (error) => error.terminal === true)
  }
})

test('aborted polling does not issue a status request', async () => {
  const controller = new AbortController()
  controller.abort()
  let called = false
  await assert.rejects(pollReview({ jobId: 'id', signal: controller.signal, getStatus: async () => { called = true } }), { name: 'AbortError' })
  assert.equal(called, false)
})

test('pausing an active wait cancels immediately', async () => {
  const controller = new AbortController()
  const pending = wait(10000, controller.signal)
  controller.abort()
  await assert.rejects(pending, { name: 'AbortError' })
})
