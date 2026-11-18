;window.PageEventsRegister = {
  template: '#page-events-register',
  computed: {
    eventName() {
      // The scanner page is public: the name travels with the check-in answer
      // rather than costing an authenticated GET /events/{id}.
      return (this.lastScan && this.lastScan.event_name) || ''
    },
    shownBands() {
      return (this.lastScan && this.lastScan.bands) || []
    },
    statusClass() {
      if (!this.lastScan || this.lastScan.error) return 'bad'
      // Already checked in is a STOP, not a caution: red, like an error.
      return this.lastScan.already_checked_in ? 'bad' : 'ok'
    },
    statusText() {
      if (!this.lastScan) return ''
      if (this.lastScan.error) return this.$t('events.failed')
      return this.lastScan.already_checked_in
        ? this.$t('events.checkin_already')
        : this.$t('events.checkin_valid')
    },
    statusIcon() {
      if (!this.lastScan || this.lastScan.error) return 'cancel'
      return this.lastScan.already_checked_in ? 'lock' : 'check_circle'
    }
  },
  data() {
    return {
      eventId: null,
      token: '',
      lastScan: null,
      busy: false,
      recent: [],
      pollTimer: null,
      sendCamera: {show: false, camera: 'auto'}
    }
  },
  methods: {
    async loadRecent() {
      // The door is staffed by several people at once, so the list of recent
      // check-ins lives on the server: one phone's localStorage is invisible to
      // every other phone there, and dies with the tab.
      if (!this.token) return
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/events/api/v1/checkins/${this.eventId}?k=${encodeURIComponent(this.token)}`
        )
        this.recent = Array.isArray(data) ? data : []
      } catch (error) {
        // a stale feed must never break the scanner itself
      }
    },
    closeCamera() {
      this.sendCamera.show = false
    },
    showCamera() {
      this.sendCamera.show = true
    },
    isLight(colour) {
      const hex = String(colour || '').replace('#', '')
      if (hex.length !== 6) return true
      const [r, g, b] = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16))
      return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6
    },
    recentLine(t) {
      const bands = (t.bands || []).map(b => b.name.toUpperCase()).join(' + ')
      const when = this.shortTime(t.checked_in_at)
      return [bands, when].filter(Boolean).join(' · ')
    },
    shortTime(value) {
      if (!value) return ''
      const d = new Date(value)
      return isNaN(d) ? '' : d.toTimeString().slice(0, 5)
    },
    decodeQR(res) {
      this.sendCamera.show = false
      const raw = (res && res[0] && res[0].rawValue) || ''
      // The QR payload is `ticket://<id>`; accept a pasted ticket link too.
      const id = raw.includes('ticket://')
        ? raw.split('ticket://')[1]
        : raw.split('/ticket/').pop()
      this.scan(id.trim())
    },
    async scan(ticketId) {
      if (!ticketId) return
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/events/api/v1/checkin/${encodeURIComponent(ticketId)}?k=${encodeURIComponent(this.token)}`
        )
        this.lastScan = data
      } catch (error) {
        this.lastScan = {
          error: error.response?.data?.detail || error.message || 'Unknown error'
        }
      }
    },
    finishHandover(scan) {
      // A successful hand-over returns to the scanner. Leaving the amber
      // "already checked in" card up reads as a failed scan on the very phone
      // the staff member just used -- that card is what a LATER scan should
      // show, not the receipt for this one.
      //
      // Clear the card FIRST: the hand-over is already recorded on the server,
      // so a failure in the toast must never leave a card standing that says
      // otherwise. `busy` must already be false -- unmounting a QBtn that is
      // still loading throws in Vue's patch and the card never goes away.
      this.busy = false
      this.lastScan = null
      try {
        const bands = (scan.bands || []).map(b => b.name.toUpperCase()).join(' + ')
        this.$q.notify({
          message: bands
            ? this.$t('events.checkin_done', {bands: bands})
            : this.$t('events.checkin_done_noband'),
          type: 'positive'
        })
      } catch (error) {
        // the toast is a convenience; the check-in itself is done
      }
      this.loadRecent()
    },
    async confirmCheckin() {
      if (!this.lastScan?.ticket) return
      this.busy = true
      try {
        const {data} = await LNbits.api.request(
          'POST',
          `/events/api/v1/checkin/${this.lastScan.ticket.id}`,
          null,
          {k: this.token}
        )
        this.busy = false
        this.finishHandover(data)
      } catch (error) {
        // Clear the spinner BEFORE replacing the card: unmounting a Quasar
        // QBtn while `loading` is still on throws inside Vue's patch, which
        // leaves the old card on screen.
        this.busy = false
        this.lastScan = {
          error: error.response?.data?.detail || error.message || 'Unknown error'
        }
      }
    },
  },
  beforeUnmount() {
    if (this.pollTimer) clearInterval(this.pollTimer)
  },
  async created() {
    this.eventId = this.$route.params.id
    // The scanner link carries the event's token: the page is public, the
    // hand-over endpoint is not.
    this.token = (this.$route.query && this.$route.query.k) || ''
    this.loadRecent()
    // Keep the shared list fresh while the phone sits at the door.
    this.pollTimer = setInterval(() => this.loadRecent(), 30000)
  }
}
