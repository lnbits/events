window.PageEventsTicket = {
  template: '#page-events-ticket',
  data() {
    return {
      ticketId: null,
      ticket: null,
      printMode: false,
      qrSrc: ''
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
    } catch (error) {
      LNbits.utils.notifyApiError(error)
    }
    window.addEventListener('afterprint', () => {
      this.printMode = false
    })
  }
}
