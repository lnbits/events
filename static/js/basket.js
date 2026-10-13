;window.PageEventsBasket = {
  template: '#page-events-basket',
  data() {
    return {
      basketId: null,
      basket: null,
      tickets: [],
      totals: null,
      eventName: '',
      eventImageUrl: '',
      eventCurrency: 'sat',
      eventFiatCurrency: 'GBP',
      loading: true,
      error: null,
      pollTimer: null
    }
  },
  async created() {
    this.basketId = this.$route.params.id
    await this.loadBasket()
  },
  beforeUnmount() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer)
    }
  },
  computed: {
    basketStatus() {
      return this.basket?.paid ? this.$t('events.ticket_paid') : this.$t('events.basket_pending')
    },
    buyerName() {
      return this.basket?.name || 'Anon'
    },
    formattedTotal() {
      if (!this.totals) return '-'
      const currency = (this.eventCurrency || 'sat').toUpperCase()
      if (currency === 'SAT' || currency === 'SATS') {
        return `${this.totals.total} sats`
      }
      return `${Number(this.totals.total).toFixed(2)} ${currency}`
    },
    paymentLink() {
      if (!this.basket?.satspay_charge_id) return null
      return `/satspay/${this.basket.satspay_charge_id}`
    },
    ticketSummary() {
      const count = this.tickets.length
      if (count === 1) return this.$t('events.ticket_count_one')
      return this.$t('events.ticket_count_many', {count})
    },
    bannerStyle() {
      return {
        backgroundImage: `url(${this.eventImageUrl})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        height: '180px'
      }
    }
  },
  methods: {
    async loadBasket() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/events/api/v1/baskets/${this.basketId}`
        )
        this.basket = data.basket
        this.tickets = data.tickets || []
        this.totals = data.totals || null
        this.eventName = data.event_name || data.basket?.event_id || ''
        this.eventImageUrl = data.event_image_url || ''
        this.eventCurrency = data.event_currency || 'sat'
        this.eventFiatCurrency = data.event_fiat_currency || 'GBP'
        this.loading = false
        this.error = null

        if (this.basket && !this.basket.paid) {
          this.startPolling()
        }
      } catch (error) {
        this.loading = false
        this.error = LNbits.utils.notifyApiError(error) || 'Error loading basket'
      }
    },
    ticketName(ticket) {
      return ticket.extra?.ticket_wave_title || ticket.name || 'Ticket'
    },
    shortenId(id) {
      if (!id) return ''
      return id.length > 12 ? `${id.slice(0, 6)}...${id.slice(-6)}` : id
    },
    formatDate(value) {
      const d = new Date(value)
      if (isNaN(d)) return ''
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${y}-${m}-${day}`
    },
    startPolling() {
      if (this.pollTimer) return
      this.pollTimer = setInterval(async () => {
        try {
          const {data} = await LNbits.api.request(
            'GET',
            `/events/api/v1/baskets/${this.basketId}`
          )
          this.basket = data.basket
          this.tickets = data.tickets || []
          this.totals = data.totals || null
          this.eventName = data.event_name || data.basket?.event_id || ''
          this.eventImageUrl = data.event_image_url || ''
          this.eventCurrency = data.event_currency || 'sat'
          this.eventFiatCurrency = data.event_fiat_currency || 'GBP'
          if (data.basket?.paid) {
            clearInterval(this.pollTimer)
            this.pollTimer = null
          }
        } catch (error) {
          // ignore poll errors
        }
      }, 3000)
    }
  }
}
