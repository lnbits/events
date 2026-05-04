window.PageEventsRegister = {
  template: '#page-events-register',
  data() {
    return {
      tickets: [],
      ticketsTable: {
        columns: [
          {name: 'name', align: 'left', label: 'Name', field: 'name'},
          {
            name: 'registered',
            align: 'left',
            label: 'Registered',
            field: 'registered'
          },
          {
            name: 'paid',
            align: 'left',
            label: 'Paid',
            field: 'paid'
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      sendCamera: {
        show: false,
        camera: 'auto'
      }
    }
  },
  methods: {
    hoverEmail(tmp) {
      this.tickets.data.emailtemp = tmp
    },
    closeCamera() {
      this.sendCamera.show = false
    },
    showCamera() {
      this.sendCamera.show = true
    },
    decodeQR(res) {
      this.sendCamera.show = false
      const value = res[0].rawValue.split('//')[1]
      LNbits.api
        .request('PUT', `/events/api/v1/tickets/register/${value}`)
        .then(() => {
          Quasar.Notify.create({
            type: 'positive',
            message: 'Registered!'
          })
        })
        .catch(LNbits.utils.notifyApiError)
    },
    getEventTickets() {
      LNbits.api
        .request('GET', `/events/api/v1/events/${this.eventId}/tickets`)
        .then(response => {
          this.tickets = response.data
        })
        .catch(LNbits.utils.notifyApiError)
    }
  },
  created() {
    this.eventId = this.$route.params.id
    this.getEventTickets()
  }
}
