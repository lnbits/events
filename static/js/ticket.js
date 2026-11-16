;window.PageEventsTicket = {
  template: '#page-events-ticket',
  data() {
    return {
      ticketId: null,
      ticket: null,
      eventName: '',
      ticketTypeName: '',
      ticketName: '',
      ticketEmail: '',
      purchaseDate: '',
      registered: false,
      deactivated: false,
      paid: false,
      printMode: false,
      qrSrc: ''
    }
  },
    computed: {
      ticketStatus() {
        if (this.deactivated) return this.$t('events.ticket_deactivated')
        if (this.paid) return this.$t('events.ticket_paid')
        return this.$t('events.ticket_pending')
      }
    },
    methods: {
      formatDate(value) {
        if (!value) return ''
        const d = new Date(value)
        if (isNaN(d)) return ''
        return Quasar.date.formatDate(d, 'YYYY-MM-DD HH:mm')
      },
      copyTicketUrl() {
        const url = `${window.location.origin}/events/ticket/${this.ticketId}`
        navigator.clipboard.writeText(url).then(() => {
          this.$q.notify({message: 'Link copied', type: 'positive'})
        })
      },
    copyTicketId() {
      // The claim flow asks for the BARE id; the button above copies a share
      // link. Handing out only the link is what made buyers paste a URL into
      // the promo box and get "not a recognised offer code or ticket ID".
      navigator.clipboard.writeText(this.ticketId).then(() => {
        this.$q.notify({
          message: this.$t('events.copy_ticket_id_done'),
          type: 'positive'
        })
      })
    },
    async printWindow() {
      this.printMode = true
      await this.$nextTick()
      await this.waitForPrintAssets()
      // rAF, not a timer: the sheet must be laid out before the print snapshot.
      requestAnimationFrame(() => window.print())
    },
    async waitForPrintAssets() {
      const img = document.querySelector('.ticket-print-qr')
      if (!img) return
      if (!(img.complete && img.naturalWidth > 0)) {
        await new Promise(resolve => {
          const done = () => resolve()
          img.addEventListener('load', done, {once: true})
          img.addEventListener('error', done, {once: true})
          // A print must never wait forever, but it must not print first
          // either: this was 500ms, which a phone on 4G can exceed.
          setTimeout(done, 3000)
        })
      }
      // `load` means fetched, not decoded; an undecoded image prints blank.
      try {
        await img.decode()
      } catch (error) {
        // older browsers, or an already-broken image: print as-is
      }
    },
    async loadQr() {
      // Inline the QR at page load instead of fetching it at print time. The
      // print sheet is created by the click, so a URL src starts its request
      // then and the print engine races it -- the blank-QR-on-some-PDFs report.
      const payload = `ticket://${this.ticketId}`
      this.qrSrc = `/api/v1/qrcode?data=${encodeURIComponent(payload)}`
      try {
        const response = await fetch(this.qrSrc)
        if (!response.ok) return
        const svg = await response.text()
        // Only inline what is really an SVG; otherwise keep the URL fallback.
        if (!svg.includes('<svg')) return
        this.qrSrc = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
      } catch (error) {
        // offline or blocked: the <img> keeps the URL and still tries
      }
    }
  },
  async created() {
    this.ticketId = this.$route.params.id
    this.loadQr()
    try {
      const {data} = await LNbits.api.request(
        'GET',
        `/events/api/v1/tickets/${this.ticketId}`
      )
      this.ticket = data
      this.eventName = data.event_name || ''
      this.ticketTypeName = data.ticket_type_name || ''
      this.ticketName = data.name || ''
      this.ticketEmail = data.email || ''
      this.purchaseDate = this.formatDate(data.time)
      this.registered = !!data.registered
      this.deactivated = !!data.deactivated
      this.paid = !!data.paid
    } catch (error) {
      LNbits.utils.notifyApiError(error)
    }
    window.addEventListener('afterprint', () => {
      this.printMode = false
    })
  }
}
