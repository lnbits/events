const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')

function scanner() {
  const requests = []
  const notices = []
  const context = {
    window: {},
    encodeURIComponent,
    LNbits: {
      api: {
        request: async (...args) => {
          requests.push(args)
          return {data: {id: 'ticket'}}
        }
      },
      utils: {
        notifyApiError: error => {
          throw error
        }
      }
    },
    Quasar: {Notify: {create: notice => notices.push(notice)}}
  }
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, '../static/js/register.js'), 'utf8'),
    context
  )
  const state = {
    sendCamera: {show: true},
    eventId: 'event?other=1#fragment',
    saveScannedTicket() {}
  }
  return {
    requests,
    notices,
    scan: rawValue =>
      context.window.PageEventsRegister.methods.decodeQR.call(state, [
        {rawValue}
      ])
  }
}

test('registration accepts ticket identifiers and encodes the event filter', async () => {
  for (const id of ['short-Ticket_123', 'a'.repeat(64)]) {
    const {requests, scan} = scanner()
    scan(`ticket://${id}`)
    await Promise.resolve()
    assert.equal(requests.length, 1)
    assert.equal(
      requests[0][1],
      `/events/api/v1/tickets/register/${id}?event_id=event%3Fother%3D1%23fragment`
    )
  }
})

test('registration rejects malformed QR values before making a request', () => {
  for (const value of [
    'ticket://..',
    'ticket://a/b',
    'ticket://a?event_id=other',
    'ticket://a#fragment',
    'https://ticket',
    'ticket://',
    ''
  ]) {
    const {requests, notices, scan} = scanner()
    scan(value)
    assert.equal(requests.length, 0)
    assert.equal(notices[0].type, 'negative')
  }
})
