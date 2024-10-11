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
      tickets: [],
      ticketsTable: {
        columns: [
          {name: 'id', align: 'left', label: 'ID', field: 'id'},
          {name: 'name', align: 'left', label: 'Name', field: 'name'},
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
      LNbits.api
        .request('GET', '/events/api/v1/register/ticket/' + res.split('//')[1])
        .then(response => {
          this.$q.notify({
            type: 'positive',
            message: 'Registered!'
          })
          setTimeout(() => {
            window.location.reload()
          }, 2000)
        })
        .catch(LNbits.utils.notifyApiError)
    },
    getEventTickets() {
      LNbits.api
        .request('GET', `/events/api/v1/eventtickets/${event_id}`)
        .then(response => {
          this.tickets = response.data.map(obj => {
            return mapEvents(obj)
          })
        })
        .catch(LNbits.utils.notifyApiError)
    }
  },
  created() {
    this.getEventTickets()
  }
})
