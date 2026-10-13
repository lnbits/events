;window.PageEventsRegister = {
  template: '#page-events-register',
  computed: {
    ticketsColumns() {
      return [
        {
          name: 'name',
          align: 'left',
          label: this.$t('events.col_name'),
          field: row => row.name || this.$t('events.anon')
        },
        {
          name: 'ticket_type',
          align: 'left',
          label: this.$t('events.col_ticket_type'),
          field: row => row.ticket_type_name || '-'
        },
        {
          name: 'id',
          align: 'left',
          label: 'Ticket ID',
          field: 'id'
        }
      ]
    }
  },
  data() {
    return {
      eventName: '',
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
      lastScan: null,
      ticketTypes: []
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
      if (!ticket.name) ticket.name = 'Anon'
      if (ticket.ticket_type_id && this.ticketTypes.length) {
        const tt = this.ticketTypes.find(t => t.id === ticket.ticket_type_id)
        if (tt) ticket.ticket_type_name = tt.name
      }
      const existingIndex = this.tickets.findIndex(t => t.id === ticket.id)
      if (existingIndex >= 0) {
        this.tickets.splice(existingIndex, 1)
      }
      this.tickets.unshift(ticket)
      Quasar.LocalStorage.set(this.storageKey(), this.tickets)
    },
    resolveTypeName(ticket) {
      if (ticket.ticket_type_id && this.ticketTypes.length) {
        const tt = this.ticketTypes.find(t => t.id === ticket.ticket_type_id)
        if (tt) ticket.ticket_type_name = tt.name
      }
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
        .then(response => {
          this.saveScannedTicket(response.data)
          this.lastScan = {success: true, ticket: response.data}
        })
        .catch(error => {
          this.lastScan = {
            success: false,
            ticketId: value,
            error:
              error.response?.data?.detail || error.message || 'Unknown error'
          }
        })
    }
  },
  async created() {
    this.eventId = this.$route.params.id
    try {
      const {data} = await LNbits.api.request(
        'GET',
        `/events/api/v1/events/${this.eventId}`
      )
      this.eventName = data.name || ''
    } catch (error) {
      // ignore
    }
    try {
      const {data} = await LNbits.api.request(
        'GET',
        `/events/api/v1/ticket-types/${this.eventId}`
      )
      this.ticketTypes = data || []
    } catch (error) {
      this.ticketTypes = []
    }
    this.loadScannedTickets()
    this.tickets.forEach(t => this.resolveTypeName(t))
  }
}
