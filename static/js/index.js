const mapEvents = function (obj) {
  obj.date = Quasar.date.formatDate(new Date(obj.time), 'YYYY-MM-DD HH:mm')
  obj.fsat = new Intl.NumberFormat(LOCALE).format(obj.price_per_ticket)
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
            name: 'canceled',
            align: 'left',
            label: 'Canceled',
            field: row => {
              if (row.extra.conditional && row.canceled) {
                return 'Yes'
              }
              return 'No'
            }
          },
          {
            name: 'price_per_ticket',
            align: 'left',
            label: 'Price',
            field: row => {
              if (row.currency != 'sats') {
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
          },
          {name: 'info', align: 'left', label: 'Info', field: 'info'},
          {name: 'banner', align: 'left', label: 'Banner', field: 'banner'}
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
          console.log(this.events)
          this.checkCanceledEvents()
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

    openEventDialog(data = false) {
      if (data && data.id) {
        this.formDialog.data = {...data}
      } else {
        this.formDialog.data = {
          extra: {
            conditional: false,
            min_tickets: 1
          }
        }
      }
      this.formDialog.show = true
    },
    resetEventDialog() {
      this.formDialog.show = false
      this.formDialog.data = {}
    },

    createEvent(wallet, data) {
      LNbits.api
        .request('POST', '/events/api/v1/events', wallet.adminkey, data)
        .then(response => {
          this.events.push(mapEvents(response.data))
          this.resetEventDialog()
        })
        .catch(LNbits.utils.notifyApiError)
    },
    updateformDialog(formId) {
      const link = _.findWhere(this.events, {id: formId})
      this.openEventDialog(link)
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
          this.resetEventDialog()
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
    },
    async checkCanceledEvents() {
      const events = this.events
        .filter(event => event.extra.conditional)
        .filter(e => !e.canceled)
      if (!events.length) return
      const now = new Date()
      events.forEach(async ev => {
        if (new Date(ev.closing_date) < now && ev.sold < ev.extra.min_tickets) {
          const {data} = await LNbits.api.request(
            'PUT',
            '/events/api/v1/events/' + ev.id + '/cancel',
            _.findWhere(this.g.user.wallets, {id: ev.wallet}).adminkey
          )
          Quasar.Notify.create({
            type: 'warning',
            message: `Event ${ev.name} has been canceled and refunds have been issued.`,
            icon: null
          })
          this.events = this.events.map(e =>
            e.id === ev.id ? mapEvents(data) : e
          )
        }
      })
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

/* 
{
  "id": "agNkaiTXbxa8KShW4grZUQ",
  "wallet": "12f58510dc5a46ffb8e95e7fc336c3da",
  "name": "test conditional",
  "info": "## Conditional Event\n\nMust sell 5 tickets\n\nAsks for refund lnaddress",
  "closing_date": "2025-08-22",
  "canceled": false,
  "event_start_date": "2025-08-23",
  "event_end_date": "2025-08-31",
  "currency": "EUR",
  "amount_tickets": 10,
  "price_per_ticket": 0.10000000149011612,
  "time": "2025-08-21T09:22:26.863944",
  "sold": 0,
  "banner": null,
  "extra": {
    "promo_codes": [],
    "conditional": true,
    "min_tickets": 5
  },
  "date": "2025-08-21 09:22",
  "fsat": "0.1",
  "displayUrl": "/events/agNkaiTXbxa8KShW4grZUQ"
}
*/
