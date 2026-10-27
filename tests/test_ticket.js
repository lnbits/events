const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')

for (const paid of [false, true]) {
  test(`ticket paid=${paid} handles payment after redirect`, async () => {
    const sockets = []
    const context = {
      window: {
        location:
          'https://tickets.example/events/ticket/ticket?ignored=1#ignored',
        addEventListener() {}
      },
      URL,
      encodeURIComponent,
      WebSocket: class {
        constructor(url) {
          this.url = url
          this.closed = false
          sockets.push(this)
        }
        close() {
          this.closed = true
        }
      },
      LNbits: {
        api: {request: async () => ({data: {paid}})},
        utils: {
          notifyApiError: error => {
            throw error
          }
        }
      }
    }
    vm.runInNewContext(
      fs.readFileSync(path.join(__dirname, '../static/js/ticket.js'), 'utf8'),
      context
    )
    const component = context.window.PageEventsTicket
    const state = {...component.data(), $route: {params: {id: 'ticket'}}}
    await component.created.call(state)
    assert.equal(sockets.length, paid ? 0 : 1)
    if (!paid) {
      const socket = sockets[0]
      assert.equal(
        socket.url,
        'wss://tickets.example/events/api/v1/tickets/ws/ticket'
      )
      socket.onmessage({data: JSON.stringify({paid: false})})
      assert.equal(state.ticket.paid, false)
      socket.onmessage({data: JSON.stringify({paid: true})})
      assert.equal(state.ticket.paid, true)
      assert.equal(socket.closed, true)
      socket.closed = false
      component.beforeUnmount.call(state)
      assert.equal(socket.closed, true)
    }
  })
}
