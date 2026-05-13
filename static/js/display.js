window.PageEventsDisplay = {
  template: '#page-events-display',
  data() {
    return {
      eventErrorLabel: '',
      event: null,
      paymentReq: null,
      redirectUrl: null,
      formDialog: {
        show: false,
        data: {
          name: '',
          email: '',
          refund: '',
          nostr_identifier: '',
          ticket_wave_id: null,
          payment_method: 'lightning'
        }
      },
      ticketLink: {
        show: false,
        data: {
          link: ''
        }
      },
      receive: {
        show: false,
        status: 'pending',
        paymentReq: null,
        isFiat: false
      },
      paymentDismissMsg: null,
      paymentWebsocket: null
    }
  },
  async created() {
    this.eventId = this.$route.params.id
    this.event = await this.getEvent()
  },
  computed: {
    formatDescription() {
      return LNbits.utils.convertMarkdown(this.event?.info || '')
    },
    activeTicketWaves() {
      const today = new Date().toISOString().slice(0, 10)
      return (this.event?.extra?.ticket_waves || []).filter(
        wave =>
          wave.amount_tickets > 0 &&
          wave.opening_date <= today &&
          wave.closing_date >= today
      )
    },
    selectedTicketWave() {
      return (
        this.activeTicketWaves.find(
          wave => wave.id === this.formDialog.data.ticket_wave_id
        ) ||
        this.activeTicketWaves[0] ||
        null
      )
    },
    showTicketWaveSelector() {
      return this.activeTicketWaves.length > 1
    },
    allowFiatCheckout() {
      return Boolean(this.selectedTicketWave?.allow_fiat)
    },
    fiatCheckoutLabel() {
      if (!this.allowFiatCheckout) return 'Fiat'
      const unit = ['sat', 'sats'].includes(
        (this.selectedTicketWave?.currency || '').toLowerCase()
      )
        ? this.selectedTicketWave?.fiat_currency
        : this.selectedTicketWave?.currency
      return `Fiat (${(unit || 'GBP').toUpperCase()})`
    },
    allowEmailNotifications() {
      return Boolean(this.event?.extra?.email_notifications)
    },
    allowNostrNotifications() {
      return Boolean(this.event?.extra?.nostr_notifications)
    }
  },
  methods: {
    async getEvent() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/events/api/v1/events/${this.eventId}`
        )
        const activeWaves = (data.extra?.ticket_waves || []).filter(wave => {
          const today = new Date().toISOString().slice(0, 10)
          return (
            wave.amount_tickets > 0 &&
            wave.opening_date <= today &&
            wave.closing_date >= today
          )
        })
        this.formDialog.data.ticket_wave_id =
          activeWaves.length === 1 ? activeWaves[0].id : null
        return data
      } catch (error) {
        this.eventErrorLabel = 'Event unavailable.'
        LNbits.utils.notifyApiError(error)
      }
    },
    resetForm(e) {
      e.preventDefault()
      this.formDialog.data.name = ''
      this.formDialog.data.email = ''
      this.formDialog.data.refund = ''
      this.formDialog.data.nostr_identifier = ''
      this.formDialog.data.ticket_wave_id =
        this.activeTicketWaves.length === 1
          ? this.activeTicketWaves[0].id
          : null
      this.formDialog.data.payment_method = 'lightning'
    },

    closeReceiveDialog() {
      if (this.paymentDismissMsg) {
        this.paymentDismissMsg()
        this.paymentDismissMsg = null
      }
      if (this.paymentWebsocket) {
        this.paymentWebsocket.close()
        this.paymentWebsocket = null
      }
    },
    nameValidation(val) {
      const regex = /[`!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?~]/g
      return (
        !regex.test(val) ||
        'Please enter valid name. No special character allowed.'
      )
    },
    emailValidation(val) {
      const regex = /^[\w\.-]+@[a-zA-Z\d\.-]+\.[a-zA-Z]{2,}$/
      return regex.test(val) || 'Please enter valid email.'
    },
    paymentSuccess(paymentHash) {
      if (this.paymentDismissMsg) {
        this.paymentDismissMsg()
        this.paymentDismissMsg = null
      }
      this.paymentReq = null
      this.formDialog.data.name = ''
      this.formDialog.data.email = ''
      this.formDialog.data.refund = ''
      this.formDialog.data.nostr_identifier = ''
      this.formDialog.data.ticket_wave_id =
        this.activeTicketWaves.length === 1
          ? this.activeTicketWaves[0].id
          : null
      this.formDialog.data.payment_method = 'lightning'
      Quasar.Notify.create({
        type: 'positive',
        message: 'Sent, thank you!',
        icon: null
      })
      this.receive = {
        show: false,
        status: 'complete',
        paymentReq: null,
        isFiat: false
      }
      this.ticketLink = {
        show: true,
        data: {
          link: `/events/ticket/${paymentHash}`
        }
      }
      window.open(`/events/ticket/${paymentHash}`, '_blank', 'noopener')
    },
    async createInvoice() {
      try {
        const {data} = await LNbits.api.request(
          'POST',
          `/events/api/v1/tickets/${this.eventId}`,
          null,
          {
            name: this.formDialog.data.name,
            email: this.formDialog.data.email,
            ticket_wave_id: this.formDialog.data.ticket_wave_id || null,
            promo_code: this.formDialog.data.promo_code || null,
            refund_address: this.formDialog.data.refund || null,
            nostr_identifier: this.formDialog.data.nostr_identifier || null,
            payment_method: this.allowFiatCheckout
              ? this.formDialog.data.payment_method
              : 'lightning'
          }
        )
        const isFiat = Boolean(data.is_fiat)
        this.paymentReq = isFiat
          ? data.fiat_payment_request || null
          : data.payment_request
        this.paymentHash = data.payment_hash

        this.paymentDismissMsg = Quasar.Notify.create({
          timeout: 0,
          message: 'Waiting for payment...'
        })
        this.receive = {
          show: true,
          status: 'pending',
          paymentReq: this.paymentReq,
          isFiat
        }
        if (isFiat && this.paymentReq) {
          window.open(this.paymentReq, '_blank', 'noopener')
        }
        this.paymentWatcher(this.paymentHash)
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    paymentWatcher(paymentHash) {
      if (this.paymentWebsocket) {
        this.paymentWebsocket.close()
      }

      const url = new URL(window.location)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      url.pathname = `/events/api/v1/tickets/ws/${paymentHash}`
      url.search = ''
      url.hash = ''

      const ws = new WebSocket(url.toString())
      this.paymentWebsocket = ws

      ws.onmessage = event => {
        const data = JSON.parse(event.data)
        if (data.paid === true) {
          this.paymentSuccess(paymentHash)
          ws.close()
        }
      }
      ws.onerror = error => {
        console.error('WebSocket error:', error)
      }
      ws.onclose = () => {
        if (this.paymentWebsocket === ws) {
          this.paymentWebsocket = null
        }
      }
    }
  }
}
