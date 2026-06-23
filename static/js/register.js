window.PageEventsRegister = {
  template: '#page-events-register',
  computed: {
    ticketsColumns() {
      return [
        {
          name: 'name',
          align: 'left',
          label: this.$t('events.col_name'),
          field: 'name'
        },
        {
          name: 'email',
          align: 'left',
          label: this.$t('email'),
          field: 'email'
        },
        {
          name: 'id',
          align: 'left',
          label: this.$t('id'),
          field: 'id',
          format: val => this.shortId(val)
        }
      ]
    }
  },
  data() {
    return {
      tickets: [],
      ticketsTable: {
        pagination: {
          rowsPerPage: 10
        }
      },
      sendCamera: {
        show: false,
        camera: 'auto'
      },
      lastScan: null
    }
  },
  methods: {
    storageKey() {
      return `events_scanned_${this.eventId}`
    },
    loadScannedTickets() {
      this.tickets = Quasar.LocalStorage.getItem(this.storageKey()) || []
    },
    saveScannedTicket(ticket) {
      this.tickets.unshift(ticket)
      Quasar.LocalStorage.set(this.storageKey(), this.tickets)
    },
    closeCamera() {
      this.sendCamera.show = false
    },
    showCamera() {
      this.sendCamera.show = true
    },
    shortId(id) {
      return id ? `${id.slice(0, 6)}...${id.slice(-4)}` : ''
    },
    decodeQR(res) {
      this.sendCamera.show = false
      const value = res[0].rawValue.split('//')[1]
      LNbits.api
        .request('PUT', `/events/api/v1/tickets/register/${value}`)
        .then(response => {
          this.saveScannedTicket(response.data)
          this.lastScan = {success: true, ticket: response.data}
          Quasar.Notify.create({type: 'positive', message: 'Registered!'})
        })
        .catch(error => {
          this.lastScan = {
            success: false,
            ticketId: value,
            error:
              error.response?.data?.detail || error.message || 'Unknown error'
          }
          LNbits.utils.notifyApiError(error)
        })
    }
  },
  created() {
    this.eventId = this.$route.params.id
    this.loadScannedTickets()
  }
}
