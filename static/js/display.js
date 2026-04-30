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
    this.event = await this.getEvent()
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
    async createInvoice() {
      try {
        const {data} = await LNbits.api.request(
          'POST',
          `/events/api/v1/tickets/${this.eventId}`,
          null,
          {
            name: this.formDialog.data.name,
            email: this.formDialog.data.email,
            refund: this.formDialog.data.refund || null
          }
        )
        this.paymentReq = data.payment_request
        this.paymentHash = data.payment_hash

        dismissMsg = Quasar.Notify.create({
          timeout: 0,
          message: 'Waiting for payment...'
        })

        this.receive = {
          show: true,
          status: 'pending',
          paymentReq: this.paymentReq
        }
        //TODO: use websockets
        paymentChecker = setInterval(async () => {
          try {
            const res = await LNbits.api.request(
              'GET',
              `/events/api/v1/tickets/${this.eventId}/${this.paymentHash}`
            )
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
                  link: `/events/ticket/${res.data.id}`
                }
              }
              setTimeout(() => {
                window.location.href = `/events/ticket/${res.data.id}`
              }, 5000)
            }
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        }, 2000)
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    }
  }
}
