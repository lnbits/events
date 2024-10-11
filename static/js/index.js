const mapEvents = function (obj) {
  obj.date = Quasar.date.formatDate(
    new Date(obj.time * 1000),
    'YYYY-MM-DD HH:mm'
  )
  obj.fsat = new Intl.NumberFormat(LOCALE).format(obj.amount)
  obj.displayUrl = ['/events/', obj.id].join('')
  return obj
}

window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  data() {
    return {
      events: [],
      tickets: [],
      currencies: [],
      eventsTable: {
        columns: [
          {name: 'id', align: 'left', label: 'ID', field: 'id'},
          {name: 'name', align: 'left', label: 'Name', field: 'name'},
          {name: 'info', align: 'left', label: 'Info', field: 'info'},
          {name: 'banner', align: 'left', label: 'Banner', field: 'banner'},
          {
            name: 'event_start_date',
            align: 'left',
            label: 'Start date',
            field: 'event_start_date'
          },
          {
            name: 'event_end_date',
            align: 'left',
            label: 'End date',
            field: 'event_end_date'
          },
          {
            name: 'closing_date',
            align: 'left',
            label: 'Ticket close',
            field: 'closing_date'
          },
          {
            name: 'price_per_ticket',
            align: 'left',
            label: 'Price',
            field: row => {
              if (row.currency != 'sat') {
                return LNbits.utils.formatCurrency(
                  row.price_per_ticket.toFixed(2),
                  row.currency
                )
              }
              return row.price_per_ticket
            }
          },
          {
            name: 'amount_tickets',
            align: 'left',
            label: 'No tickets',
            field: 'amount_tickets'
          },
          {
            name: 'sold',
            align: 'left',
            label: 'Sold',
            field: 'sold'
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      ticketsTable: {
        columns: [
          {name: 'id', align: 'left', label: 'ID', field: 'id'},
          {name: 'event', align: 'left', label: 'Event', field: 'event'},
          {name: 'name', align: 'left', label: 'Name', field: 'name'},
          {name: 'email', align: 'left', label: 'Email', field: 'email'},
          {
            name: 'registered',
            align: 'left',
            label: 'Registered',
            field: 'registered'
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      formDialog: {
        show: false,
        data: {}
      }
    }
  },
  methods: {
    getTickets() {
      LNbits.api
        .request(
          'GET',
          '/events/api/v1/tickets?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        .then(response => {
          this.tickets = response.data
            .map(function (obj) {
              return mapEvents(obj)
            })
            .filter(e => e.paid)
        })
    },
    deleteTicket(ticketId) {
      const tickets = _.findWhere(this.tickets, {id: ticketId})

      LNbits.utils
        .confirmDialog('Are you sure you want to delete this ticket')
        .onOk(() => {
          LNbits.api
            .request(
              'DELETE',
              '/events/api/v1/tickets/' + ticketId,
              _.findWhere(this.g.user.wallets, {id: tickets.wallet}).inkey
            )
            .then(response => {
              this.tickets = _.reject(this.tickets, function (obj) {
                return obj.id == ticketId
              })
            })
            .catch(function (error) {
              LNbits.utils.notifyApiError(error)
            })
        })
    },
    exportticketsCSV() {
      LNbits.utils.exportCSV(this.ticketsTable.columns, this.tickets)
    },
    getEvents() {
      LNbits.api
        .request(
          'GET',
          '/events/api/v1/events?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        .then(response => {
          this.events = response.data.map(function (obj) {
            return mapEvents(obj)
          })
        })
    },
    sendEventData() {
      const wallet = _.findWhere(this.g.user.wallets, {
        id: this.formDialog.data.wallet
      })
      const data = this.formDialog.data

      if (data.id) {
        this.updateEvent(wallet, data)
      } else {
        this.createEvent(wallet, data)
      }
    },

    createEvent(wallet, data) {
      LNbits.api
        .request('POST', '/events/api/v1/events', wallet.adminkey, data)
        .then(response => {
          this.events.push(mapEvents(response.data))
          this.formDialog.show = false
          this.formDialog.data = {}
        })
        .catch(LNbits.utils.notifyApiError)
    },
    updateformDialog(formId) {
      const link = _.findWhere(this.events, {id: formId})
      this.formDialog.data = {...link}
      this.formDialog.show = true
    },
    updateEvent(wallet, data) {
      LNbits.api
        .request(
          'PUT',
          '/events/api/v1/events/' + data.id,
          wallet.adminkey,
          data
        )
        .then(response => {
          this.events = _.reject(this.events, function (obj) {
            return obj.id == data.id
          })
          this.events.push(mapEvents(response.data))
          this.formDialog.show = false
          this.formDialog.data = {}
        })
        .catch(LNbits.utils.notifyApiError)
    },
    deleteEvent(eventsId) {
      const events = _.findWhere(this.events, {id: eventsId})

      LNbits.utils
        .confirmDialog('Are you sure you want to delete this form link?')
        .onOk(() => {
          LNbits.api
            .request(
              'DELETE',
              '/events/api/v1/events/' + eventsId,
              _.findWhere(this.g.user.wallets, {id: events.wallet}).adminkey
            )
            .then(response => {
              this.events = _.reject(this.events, function (obj) {
                return obj.id == eventsId
              })
            })
            .catch(LNbits.utils.notifyApiError(error))
        })
    },
    exporteventsCSV() {
      LNbits.utils.exportCSV(this.eventsTable.columns, this.events)
    }
  },
  async created() {
    if (this.g.user.wallets.length) {
      this.getTickets()
      this.getEvents()
      this.currencies = await LNbits.api.getCurrencies()
    }
  }
})
