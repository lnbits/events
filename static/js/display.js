window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  data() {
    return {
      paymentReq: null,
      redirectUrl: null,
      formDialog: {
        show: false,
        data: {
          name: '',
          email: ''
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
    this.info = event_info
    this.info = this.info.substring(1, this.info.length - 1)
    this.banner = event_banner
    await this.purgeUnpaidTickets()
  },
  computed: {
    formatDescription() {
        console.log(this.info)
        debugger
      return LNbits.utils.convertMarkdown(this.info)
    }
  },
  methods: {
    resetForm(e) {
      e.preventDefault()
      this.formDialog.data.name = ''
      this.formDialog.data.email = ''
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
          email: this.formDialog.data.email
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
    },
    async purgeUnpaidTickets() {
      try {
        await LNbits.api.request('GET', `/events/api/v1/purge/${event_id}`)
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    }
  }
})
