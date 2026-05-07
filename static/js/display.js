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
    allowFiatCheckout() {
      const currency = (this.event?.currency || '').toLowerCase()
      return this.event?.allow_fiat && !['sat', 'sats'].includes(currency)
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
            promo_code: this.formDialog.data.promo_code || null,
            refund_address: this.formDialog.data.refund || null,
            nostr_identifier: this.formDialog.data.nostr_identifier || null,
            payment_method: this.formDialog.data.payment_method
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
      url.pathname = `/api/v1/ws/${paymentHash}`
      url.search = ''
      url.hash = ''

      const ws = new WebSocket(url.toString())
      this.paymentWebsocket = ws

      ws.onmessage = event => {
        const data = JSON.parse(event.data)
        if (data.pending === false) {
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
