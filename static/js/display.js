window.PageEventsDisplay = {
  template: '#page-events-display',
  data() {
    return {
      eventName: '',
      paymentReq: null,
      redirectUrl: null,
      formDialog: {
        show: false,
        data: {
          name: '',
          email: '',
          refund: ''
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
        paymentReq: null
      }
    }
  },
  async created() {
    this.eventId = this.$route.params.id
    await this.getEvent()
  },
  computed: {
    formatDescription() {
      return LNbits.utils.convertMarkdown(this.info)
    }
  },
  methods: {
    async getEvent() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/events/api/v1/events/${this.eventId}`
        )
        this.eventName = data.event_name
        this.info = data.event_info
        this.banner = data.event_banner
        this.extra = data.event_extra
        this.hasPromoCodes = data.has_promo_codes
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    resetForm(e) {
      e.preventDefault()
      this.formDialog.data.name = ''
      this.formDialog.data.email = ''
      this.formDialog.data.refund = ''
    },

    closeReceiveDialog() {
      const checker = this.receive.paymentChecker
      dismissMsg()
      clearInterval(paymentChecker)
      setTimeout(() => {}, 10000)
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
    Invoice() {
      axios
        .post(`/events/api/v1/tickets/${event_id}`, {
          name: this.formDialog.data.name,
          email: this.formDialog.data.email,
          promo_code: this.formDialog.data.promo_code || null
        })
        .then(response => {
          this.paymentReq = response.data.payment_request
          this.paymentCheck = response.data.payment_hash

          dismissMsg = Quasar.Notify.create({
            timeout: 0,
            message: 'Waiting for payment...'
          })

          this.receive = {
            show: true,
            status: 'pending',
            paymentReq: this.paymentReq
          }
          paymentChecker = setInterval(() => {
            axios
              .post(`/events/api/v1/tickets/${event_id}/${this.paymentCheck}`, {
                event: event_id,
                event_name: event_name,
                name: this.formDialog.data.name,
                email: this.formDialog.data.email
              })
              .then(res => {
                if (res.data.paid) {
                  clearInterval(paymentChecker)
                  dismissMsg()
                  this.formDialog.data.name = ''
                  this.formDialog.data.email = ''

                  Quasar.Notify.create({
                    type: 'positive',
                    message: 'Sent, thank you!',
                    icon: null
                  })
                  this.receive = {
                    show: false,
                    status: 'complete',
                    paymentReq: null
                  }

                  this.ticketLink = {
                    show: true,
                    data: {
                      link: `/events/ticket/${res.data.ticket_id}`
                    }
                  }
                  setTimeout(() => {
                    window.location.href = `/events/ticket/${res.data.ticket_id}`
                  }, 5000)
                }
              })
              .catch(LNbits.utils.notifyApiError)
          }, 2000)
        })
        .catch(LNbits.utils.notifyApiError)
    }
  }
}
