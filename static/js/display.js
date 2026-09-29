window.PageEventsDisplay = {
  template: '#page-events-display',
  data() {
    return {
      eventErrorLabel: '',
      event: null,
      ticketTypes: [],
      itemQuantities: {},
      basketName: '',
      basketEmail: '',
      promoCodeInput: '',
      discountBreakdown: [],
      promoMessages: [],
      basketTotal: 0,
      applyingPromo: false,
      basketItems: [],
      submitting: false,
      checkoutLoading: false,
      nostrIdentifier: '',
      attendeeFields: {},
      copyDetailsToAll: {},
      ticketLink: {
        show: false,
        data: {
          link: ''
        }
      }
    }
  },
  async mounted() {
    this.eventId = this.$route.params.id
    await this.loadEvent()
    if (this.event) {
      await this.loadTicketTypes()
    }
  },
  computed: {
    formatDescription() {
      return LNbits.utils.convertMarkdown(this.event?.info || '')
    },
    basketCurrency() {
      const c = this.event?.currency || 'sat'
      return c === 'sat' ? 'sats' : c
    },
    basket() {
      return this.basketItems
        .map(item => {
          const tt = this.ticketTypes.find(t => t.id === item.ticketTypeId)
          if (!tt) return null
          return {
            ticketTypeId: tt.id,
            name: tt.name,
            quantity: item.quantity,
            price: tt.price,
            subtotal: tt.price * item.quantity
          }
        })
        .filter(Boolean)
    },
    canCheckout() {
      if (this.submitting || this.checkoutLoading) return false
      const hasItems = this.basketItems.some(
        item => item.quantity > 0
      )
      if (!hasItems) return false
      if (this.basketEmail && !/^[\w\.-]+@[a-zA-Z\d\.-]+\.[a-zA-Z]{2,}$/.test(this.basketEmail)) return false
      return true
    },
    allowEmailNotifications() {
      return Boolean(this.event?.extra?.email_notifications)
    },
    allowNostrNotifications() {
      return Boolean(this.event?.extra?.nostr_notifications)
    },
    acceptedPaymentMethods() {
      return this.event?.extra?.payment_methods || []
    }
  },
  methods: {
    async loadEvent() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/events/api/v1/events/${this.eventId}`
        )
        this.event = data
      } catch (error) {
        this.eventErrorLabel = this.$t('events.event_unavailable')
        LNbits.utils.notifyApiError(error)
      }
    },
    async loadTicketTypes() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/events/api/v1/ticket-types/${this.eventId}`
        )
        const today = new Date().toISOString().slice(0, 10)
        this.ticketTypes = data.filter(
          tt =>
            (tt.extra?.active ?? true) &&
            tt.available_from <= today &&
            tt.available_to >= today &&
            (tt.max_tickets === 0 || tt.sold < tt.max_tickets)
        )
        for (const tt of this.ticketTypes) {
          this.itemQuantities[tt.id] = 0
          this.attendeeFields[tt.id] = []
          this.copyDetailsToAll[tt.id] = false
        }
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    addToBasket(tt, qty) {
      if (qty <= 0) return
      const existing = this.basketItems.find(
        item => item.ticketTypeId === tt.id
      )
      if (existing) {
        existing.quantity = qty
      } else {
        this.basketItems.push({ticketTypeId: tt.id, quantity: qty})
      }
      this.itemQuantities[tt.id] = qty
      this.rebuildBasket()
    },
    removeFromBasket(ttId) {
      this.basketItems = this.basketItems.filter(
        item => item.ticketTypeId !== ttId
      )
      this.itemQuantities[ttId] = 0
      this.attendeeFields[ttId] = []
      this.rebuildBasket()
    },
    addToBasketBtn(tt) {
      const qty = this.itemQuantities[tt.id] || 0
      if (qty <= 0) return
      this.addToBasket(tt, qty)
    },
    rebuildBasket() {
      this.basketItems = this.basketItems.filter(
        item => item.quantity > 0
      )
      if (this.basketItems.length === 0) {
        this.discountBreakdown = []
        this.promoMessages = []
        this.basketTotal = 0
        return
      }
      let subtotal = 0
      for (const bi of this.basketItems) {
        const tt = this.ticketTypes.find(t => t.id === bi.ticketTypeId)
        if (tt) {
          subtotal += tt.price * bi.quantity
        }
      }
      this.basketTotal = subtotal
      this.discountBreakdown = []
      this.promoMessages = []
    },
    async applyPromoCode() {
      // Offer codes are matched case-insensitively by the server, but TICKET
      // IDs are case-sensitive primary keys — never upper-case what the buyer
      // typed or a valid ticket ID stops resolving.
      const codes = this.promoCodeInput
        .split(',')
        .map(c => c.trim())
        .filter(c => c.length > 0)
      if (!codes.length) {
        this.rebuildBasket()
        return
      }
      if (!this.basketItems.length) return
      this.applyingPromo = true
      try {
        const items = this.basketItems.map(bi => ({
          ticket_type_id: bi.ticketTypeId,
          quantity: bi.quantity
        }))
        const {data} = await LNbits.api.request(
          'POST',
          `/events/api/v1/promo/validate/${this.eventId}`,
          null,
          {codes, items}
        )
        this.basketTotal = data.total
        this.discountBreakdown = (data.discounts_applied || []).map(d => ({
          label: `${d.code}: ${d.amount_saved} ${this.basketCurrency}`
        }))
        // An offer that needs a ticket ID reports what it still wants, so the
        // buyer is told to add one instead of seeing nothing happen.
        this.promoMessages = (data.pending || []).map(p => ({
          kind: 'pending',
          label: this.$t('events.promo_pending_ticket', {code: p.code})
        }))
        // A token that could not be used says why, instead of silently doing
        // nothing (which is indistinguishable from a mistyped code).
        this.promoMessages = this.promoMessages.concat(
          (data.rejections || []).map(r => ({
            kind: 'rejected',
            label: `${r.code}: ${this.promoReasonLabel(r.reason)}`
          }))
        )
        if (
          !this.discountBreakdown.length &&
          !this.promoMessages.length &&
          codes.length
        ) {
          this.promoMessages = [
            {kind: 'rejected', label: this.$t('events.promo_none_found')}
          ]
        }
      } catch (error) {
        LNbits.utils.notifyApiError(error)
        this.rebuildBasket()
      } finally {
        this.applyingPromo = false
      }
    },
    promoReasonLabel(reason) {
      const key = `events.promo_reason_${reason}`
      const label = this.$t(key)
      // $t returns the key itself when it is missing; fall back to a generic
      // message rather than showing a raw i18n key to a buyer.
      return label === key ? this.$t('events.promo_reason_generic') : label
    },
  
    async checkout() {
      if (this.checkoutLoading || !this.canCheckout) return
      this.checkoutLoading = true
      try {
        const items = this.basketItems.map(bi => ({
          ticket_type_id: bi.ticketTypeId,
          quantity: bi.quantity
        }))
        // Same as applyPromoCode: codes are case-insensitive server-side but
        // ticket IDs are not, so send what the buyer typed.
        const promo_codes = this.promoCodeInput
          .split(',')
          .map(c => c.trim())
          .filter(c => c.length > 0)
        const refundAddr = (this.event?.extra?.conditional)
          ? ''
          : undefined

        const body = {
          name: this.basketName,
          email: this.basketEmail || null,
          items,
          promo_codes,
          payment_method: null,
          fiat_provider: this.event?.extra?.fiat_provider || null,
          nostr_identifier: this.nostrIdentifier || null,
          refund_address: refundAddr || null
        }

        const {data} = await LNbits.api.request(
          'POST',
          `/events/api/v1/baskets/${this.eventId}`,
          null,
          body
        )

        const firstTicket = data.tickets?.[0]
        if (data.basket?.id) {
          this.$router.push(`/events/basket/${data.basket.id}`)
        } else if (firstTicket) {
          this.ticketLink.show = true
          this.ticketLink.data.link = `/events/ticket/${firstTicket.id}`
        }
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.checkoutLoading = false
      }
    }
  }
}
