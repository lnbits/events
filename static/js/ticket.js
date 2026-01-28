window.PageEventsTicket = {
  template: '#page-events-ticket',
  data() {
    return {
      ticketId: null,
      ticketName: null
    }
  },
  methods: {
    printWindow() {
      window.print()
    }
  },
  async created() {
    this.ticketId = this.$route.params.id
    try {
      const {data} = await LNbits.api.request(
        'GET',
        `/events/api/v1/tickets/${this.ticketId}`
      )
      this.ticketName = data.ticket_name
    } catch (error) {
      LNbits.utils.notifyApiError(error)
    }
  }
}
