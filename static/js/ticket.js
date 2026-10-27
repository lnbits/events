window.PageEventsTicket = {
  template: '#page-events-ticket',
  data() {
    return {
      ticketId: null,
      ticket: null,
      printMode: false,
      qrSrc: '',
      paymentWebsocket: null
    }
  },
  methods: {
    async printWindow() {
      this.printMode = true
      await this.$nextTick()
      await this.waitForPrintAssets()
      setTimeout(() => window.print(), 50)
    },
    async waitForPrintAssets() {
      await this.$nextTick()
      const img = document.querySelector('.ticket-print-qr')
      if (!img) return
      if (img.complete && img.naturalWidth > 0) return
      await new Promise(resolve => {
        const done = () => resolve()
        img.addEventListener('load', done, {once: true})
        img.addEventListener('error', done, {once: true})
        setTimeout(done, 500)
      })
    }
  },
  beforeUnmount() {
    this.paymentWebsocket?.close()
  },
  async created() {
    this.ticketId = this.$route.params.id
    this.qrSrc = `/api/v1/qrcode?data=${encodeURIComponent(
      `ticket://${this.ticketId}`
    )}`
    try {
      const {data} = await LNbits.api.request(
        'GET',
        `/events/api/v1/tickets/${this.ticketId}`
      )
      this.ticket = data
      if (!data.paid) {
        const url = new URL(window.location)
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
        url.pathname = `/events/api/v1/tickets/ws/${this.ticketId}`
        url.search = ''
        url.hash = ''
        this.paymentWebsocket = new WebSocket(url.toString())
        this.paymentWebsocket.onmessage = event => {
          if (JSON.parse(event.data).paid === true) {
            this.ticket.paid = true
            this.paymentWebsocket.close()
          }
        }
      }
    } catch (error) {
      LNbits.utils.notifyApiError(error)
    }
    window.addEventListener('afterprint', () => {
      this.printMode = false
    })
  }
}
