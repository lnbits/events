window.PageEvents = {
  template: '#page-events',
  computed: {
    eventsColumns() {
      return [
        {
          name: 'id',
          align: 'left',
          label: this.$t('id'),
          field: row => this.shortenId(row.id)
        },
        {
          name: 'name',
          align: 'left',
          label: this.$t('events.col_name'),
          field: 'name'
        },
        {
          name: 'event_start_date',
          align: 'left',
          label: this.$t('events.col_start_date'),
          field: 'event_start_date'
        },
        {
          name: 'event_end_date',
          align: 'left',
          label: this.$t('events.col_end_date'),
          field: 'event_end_date'
        },
        {
          name: 'canceled',
          align: 'left',
          label: this.$t('events.col_canceled'),
          field: row => {
            if (row.extra.conditional && row.canceled) {
              return this.$t('events.col_yes')
            }
            return this.$t('events.col_no')
          }
        }
      ]
    },
    ticketsColumns() {
      return [
        {
          name: 'event',
          align: 'left',
          label: this.$t('events.col_event'),
          field: row => this.shortenId(row.event)
        },
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
          name: 'registered',
          align: 'left',
          label: this.$t('events.col_registered'),
          field: 'registered'
        },
        {
          name: 'nostr',
          align: 'left',
          label: this.$t('events.col_nostr'),
          field: row => row.extra?.nostr_identifier || ''
        },
        {
          name: 'deactivated',
          align: 'left',
          label: this.$t('events.col_deactivated'),
          field: row => row.extra?.deactivated ? this.$t('events.col_yes') : this.$t('events.col_no')
        },
        {
          name: 'purchase_date',
          align: 'left',
          label: this.$t('events.col_purchase_date'),
          field: row => {
            const d = new Date(row.time)
            return isNaN(d) ? '' : this.formatISODate(d)
          }
        },
        {
          name: 'promo_code',
          align: 'left',
          label: this.$t('events.col_promo_code'),
          field: row => row.extra.applied_promo_code || ''
        },
        {name: 'id', align: 'left', label: this.$t('id'), field: 'id'}
      ]
    }
  },
  data() {
    return {
      events: [],
      tickets: [],
      allPaidTickets: [],
      resendingTicketEmails: [],
      resendingAllEmailsFor: [],
      isUploadingTicketTemplate: false,
      currencies: [],
      eventsTable: {
        pagination: {
          rowsPerPage: 10
        }
      },
      ticketsTable: {
        loading: false,
        pagination: {
          sortBy: 'time',
          descending: true,
          page: 1,
          rowsPerPage: 10,
          rowsNumber: 10
        }
      },
      formDialog: {
        show: false,
        data: {
          currency: 'sats',
          allow_fiat: false,
          fiat_currency: 'GBP',
          extra: {
            promo_codes: [],
            notification_subject: '',
            notification_body: ''
          }
        }
      },
       ticketTypeDialog: {
         show: false,
         eventId: null,
         isEdit: false,
         wallet: null,
         data: {
           id: null,
           name: '',
           description: '',
           image_url: null,
           price: 0,
            max_tickets: 0,
            available_from: '',
            available_to: '',
            sort_order: 0,
active: true,
            show_remaining: false,
            remaining_threshold: 0
           }
         },
       ticketTypesByEvent: {},
      promoCodesDialog: {
        show: false,
        data: {
          id: null,
          wallet: null,
          name: '',
          extra: {
            promo_codes: []
          }
        }
      },
      promoDiscountTypes: {},
      editPromoCodeDialog: {
        show: false,
        eventId: null,
        codeIndex: -1,
        data: {
          code: '',
          type: 'code',
          discount_percent: null,
          discount_fixed: null,
          active: true,
          combinable: true,
          max_uses: null,
          used_count: 0,
          redemptions_per_ticket: 1,
          ticket_type_ids: [],
          max_tickets: null
        },
        discountType: 'percent'
      },
      watchonlyWallets: [],
      paymentMethods: {
        ln: false,
        onchain: false,
        fiat: false
      },
      emailAllDialog: {
        show: false,
        eventId: null,
        subject: '',
        message: '',
        loading: false
      }
    }
  },
  methods: {
    formatISODate(value) {
      const d = new Date(value)
      if (isNaN(d)) return ''
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${y}-${m}-${day}`
    },
    ticketTypeChipLabel(tt) {
      const event = this.events.find(e => e.id === tt.event_id)
      const currency = event?.currency || 'sat'
      const price = this.isFiatCurrency(currency)
        ? LNbits.utils.formatCurrency(
            Number(tt.price || 0).toFixed(2),
            currency
          )
        : `${tt.price} sats`
      return this.$t('events.tt_chip', {
        name: tt.name,
        price,
        sold: tt.sold || 0,
        max: tt.max_tickets
      })
    },
    soldTicketsForType(ttId) {
      return this.allPaidTickets.filter(
        ticket =>
          ticket.paid &&
          ticket.ticket_type_id === ttId
      ).length
    },
    shortenId(value) {
      if (!value) return ''
      return value.length > 4 ? `${value.slice(0, 4)}...` : value
    },
    isFiatCurrency(currency) {
      return !['sat', 'sats'].includes((currency || '').toLowerCase())
    },
    getEventCurrency(eventId) {
      const event = this.events.find(e => e.id === eventId)
      return event?.currency || 'sats'
    },
    normalizePromoSource(code) {
      const src =
        code?.source ||
        (code?.type === 'ticket' ? {require_ticket: true} : {})
      const events = Array.isArray(src.event_ids)
        ? src.event_ids.filter(Boolean)
        : []
      const types = Array.isArray(src.ticket_type_ids)
        ? src.ticket_type_ids.filter(Boolean)
        : []
      return {
        // `require_ticket` is an ADDITIONAL condition on top of the offer code:
        // the offer applies only when an eligible ticket id is supplied too.
        // The legacy `type: 'ticket'` and interim `kind: 'ticket'` both map here.
        require_ticket:
          src.require_ticket === true ||
          src.kind === 'ticket' ||
          code?.type === 'ticket',
        // Empty source scope = this event only (the backend default).
        event_ids: events.length ? events : null,
        ticket_type_ids: types.length ? types : null,
        move: !!src.move,
        credit: src.credit === 'paid' ? 'paid' : 'none'
      }
    },
    normalizePromoCodes(promoCodes = []) {
      return promoCodes
        .map(code => {
          const source = this.normalizePromoSource(code)
          code = {
            redemptions_per_ticket: 1,
            ...code,
            source
          }
          // The legacy `type` axis is retired; `source.require_ticket` carries
          // it now. The code is ALWAYS the offer code — never blanked, since it
          // is what identifies the offer to the buyer and what max_uses counts.
          delete code.type
          // Ticket-type scoping: empty selection = whole basket (null).
          const scope = Array.isArray(code.ticket_type_ids)
            ? code.ticket_type_ids.filter(Boolean)
            : []
          code.ticket_type_ids = scope.length ? scope : null
          if (!code.max_tickets) code.max_tickets = null
          return {
            ...code,
            code: (code.code || '').trim().toUpperCase()
          }
        })
        // A rule without a ticket requirement needs a code to be redeemable;
        // one WITH a ticket requirement may legitimately have none (it is then
        // activated by any eligible ticket id).
        .filter(code => code.source.require_ticket || code.code !== '')
    },
    grantedTicketTypeName(grant) {
      // A granted type is named by id only; look it up across the loaded
      // events, since it need not belong to the rule's own event.
      if (!grant || !grant.ticket_type_id) return ''
      for (const types of Object.values(this.ticketTypesByEvent || {})) {
        const match = (types || []).find(tt => tt.id === grant.ticket_type_id)
        if (match) return match.name
      }
      return grant.ticket_type_id
    },
    promoChipLabel(code, currency) {
      const uses =
        code.max_uses != null && code.max_uses > 0
          ? ` (${code.used_count || 0}/${code.max_uses})`
          : ''
      if (code.grants) {
        // A grant discounts nothing, so the old label rendered as a blank
        // " - " and the rule looked purposeless. Name what it adds instead.
        const prefix = code.code ? code.code.toUpperCase() + ' ' : ''
        return `${prefix}\u2192 ${this.grantedTicketTypeName(code.grants)}${uses}`
      }
      const amount =
        code.discount_percent != null
          ? code.discount_percent + '%'
          : code.discount_fixed != null
            ? ` ${code.discount_fixed} ${currency === 'sat' ? 'sats' : currency}`
            : ''
      return `${(code.code || '').toUpperCase()} - ${amount}${uses}`
    },
    ticketTypeOptions(eventId) {
      const tts = this.ticketTypesByEvent?.[eventId] || []
      return tts.map(tt => ({
        label: `${tt.name} (${tt.price})`,
        value: tt.id
      }))
    },
    sourceEventOptions(targetEventId) {
      return (this.events || []).map(ev => ({
        label: ev.id === targetEventId ? `${ev.name} — this event` : ev.name,
        value: ev.id
      }))
    },
    sourceEventIds(source, targetEventId) {
      const picked = Array.isArray(source?.event_ids)
        ? source.event_ids.filter(Boolean)
        : []
      // No source event named = this event only (the backend default).
      return picked.length ? picked : [targetEventId].filter(Boolean)
    },
    sourceTicketTypeOptions(source, targetEventId) {
      const out = []
      for (const id of this.sourceEventIds(source, targetEventId)) {
        for (const tt of this.ticketTypesByEvent?.[id] || []) {
          out.push({label: `${tt.name} (${tt.price})`, value: tt.id})
        }
      }
      return out
    },
    loadPromoScopeTicketTypes(codes, targetEventId) {
      if (!this.ticketTypesByEvent?.[targetEventId]) {
        this.loadTicketTypes(targetEventId)
      }
      for (const code of codes || []) {
        if (!code?.source?.require_ticket) continue
        for (const id of code.source.event_ids || []) {
          if (id !== targetEventId && !this.ticketTypesByEvent?.[id]) {
            this.loadTicketTypes(id)
          }
        }
      }
    },
    templateDownloadUrl() {
      return '/events/static/image/ticket.jpg'
    },
    async uploadAssetFile(file) {
      const form = new FormData()
      form.append('file', file)
      form.append('public_asset', 'true')
      const {data} = await LNbits.api.request(
        'POST',
        '/api/v1/assets?public_asset=true',
        null,
        form
      )
      return data.id
    },
    getAllTickets() {
      LNbits.api
        .request(
          'GET',
          '/events/api/v1/tickets?all_wallets=true',
          this.g.user.wallets[0].adminkey
        )
        .then(response => {
          this.allPaidTickets = response.data.filter(ticket => ticket.paid)
        })
        .catch(LNbits.utils.notifyApiError)
    },
    getTickets(props) {
      this.ticketsTable.loading = true
      const params = LNbits.utils.prepareFilterQuery(this.ticketsTable, props)
      LNbits.api
        .request(
          'GET',
          `/events/api/v1/tickets/paginated?all_wallets=true&${params}`,
          this.g.user.wallets[0].adminkey
        )
        .then(response => {
          this.tickets = response.data.data
          this.ticketsTable.pagination.rowsNumber = response.data.total
        })
        .catch(LNbits.utils.notifyApiError)
        .finally(() => {
          this.ticketsTable.loading = false
        })
    },
    deleteTicket(ticketId) {
      const ticket = _.findWhere(this.tickets, {id: ticketId})
      const wallet = _.findWhere(this.g.user.wallets, {id: ticket.wallet})

      LNbits.utils
        .confirmDialog(this.$t('events.delete_ticket_confirm'))
        .onOk(() => {
          LNbits.api
            .request(
              'DELETE',
              '/events/api/v1/tickets/' + ticketId,
              wallet.adminkey
            )
            .then(async () => {
              await this.getTickets()
              await this.getAllTickets()
            })
            .catch(LNbits.utils.notifyApiError)
        })
    },
    resendTicketEmail(ticket) {
      if (!ticket.paid || !ticket.email) return
      const wallet = _.findWhere(this.g.user.wallets, {id: ticket.wallet})
      if (!wallet) return

      this.resendingTicketEmails.push(ticket.id)
      LNbits.api
        .request(
          'POST',
          '/events/api/v1/tickets/' + ticket.id + '/resend-email',
          wallet.adminkey
        )
        .then(response => {
          const result = response.data
          this.tickets = this.tickets.map(obj =>
            obj.id === ticket.id ? result.ticket : obj
          )

          if (result.email?.attempted) {
            Quasar.Notify.create({
              type: result.email.sent ? 'positive' : 'negative',
              message: result.email.sent
                ? this.$t('events.email_resent')
                : this.$t('events.email_resend_failed', {
                    error: result.email.error || this.$t('events.unknown_error')
                  }),
              icon: null
            })
          }

          if (result.nostr?.attempted) {
            Quasar.Notify.create({
              type: result.nostr.sent ? 'positive' : 'negative',
              message: result.nostr.sent
                ? this.$t('events.nostr_resent')
                : this.$t('events.nostr_resend_failed', {
                    error: result.nostr.error || this.$t('events.unknown_error')
                  }),
              icon: null
            })
          }
        })
        .catch(LNbits.utils.notifyApiError)
          .finally(() => {
          this.resendingTicketEmails = this.resendingTicketEmails.filter(
            ticketId => ticketId !== ticket.id
          )
        })
    },
    toggleTicketDeactivation(ticket) {
      const wallet = _.findWhere(this.g.user.wallets, {id: ticket.wallet})
      if (!wallet) return
      LNbits.api
        .request(
          'PUT',
          '/events/api/v1/tickets/' + ticket.id + '/deactivate',
          wallet.adminkey
        )
        .then(response => {
          const updated = response.data
          const action = updated.extra?.deactivated ? 'deactivated' : 'activated'
          this.tickets = this.tickets.map(t =>
            t.id === ticket.id ? updated : t
          )
          Quasar.Notify.create({
            type: 'positive',
            message: `Ticket ${action}.`,
            icon: null
          })
        })
        .catch(LNbits.utils.notifyApiError)
    },
    exportticketsCSV() {
      LNbits.utils.exportCSV(this.ticketsColumns, this.allPaidTickets)
    },
    getEvents() {
      LNbits.api
        .request(
          'GET',
          '/events/api/v1/events?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        .then(response => {
          this.events = response.data
          this.checkCanceledEvents()
          this.events.forEach(ev => this.loadTicketTypes(ev.id))
        })
    },
    fetchWatchOnlyWallets() {
      LNbits.api
        .request(
          'GET',
          '/watchonly/api/v1/wallet',
          this.g.user.wallets[0].adminkey
        )
        .then(response => {
          this.watchonlyWallets = (response.data || []).map(w => ({
            value: w.id,
            label: (w.title || w.name || 'Wallet') + ' - ' + w.id
          }))
        })
        .catch(() => {
          console.warn('WatchOnly extension not available, onchain disabled')
        })
    },
    sendEventData() {
      const data = this.formDialog.data
      if (!data.id) {
        data.wallet = data.extra?.ln_wallet_id || this.g.user.wallets?.[0]?.id
      }
      const wallet = _.findWhere(this.g.user.wallets, {id: data.wallet})
      if (this.paymentMethods.ln && !data.extra?.ln_wallet_id) {
        this.$q.notify({message: 'Select an LN wallet for Lightning payments.', type: 'negative'})
        return
      }
      if (this.paymentMethods.onchain && !data.extra?.onchain_wallet_id) {
        this.$q.notify({message: 'Select an onchain wallet for onchain payments.', type: 'negative'})
        return
      }
      if (data.extra?.promo_codes) {
        data.extra.promo_codes = this.normalizePromoCodes(
          data.extra.promo_codes
        )
      }
      if (!this.isFiatCurrency(data.currency)) {
        if (!data.allow_fiat) {
          data.fiat_currency = 'GBP'
        }
      }
      const methods = []
      if (this.paymentMethods.ln) methods.push('ln')
      if (this.paymentMethods.onchain) methods.push('onchain')
      if (this.paymentMethods.fiat) methods.push('fiat')
      data.extra.payment_methods = methods
      if (data.id) {
        this.updateEvent(wallet, data)
      } else {
        this.createEvent(wallet, data)
      }
    },
    openEventDialog(data = false) {
      if (data && data.id) {
        this.formDialog.data = {
          ...data,
          extra: {
            ...(data.extra || {}),
            promo_codes: [...((data.extra && data.extra.promo_codes) || [])],
          }
        }
        const pm = (data.extra && data.extra.payment_methods) || []
        this.paymentMethods.ln = pm.includes('ln')
        this.paymentMethods.onchain = pm.includes('onchain')
        this.paymentMethods.fiat = pm.includes('fiat')
        if (!data.extra.fiat_provider) {
          data.extra.fiat_provider = ''
        }
      } else {
        this.formDialog.data = {
          wallet: null,
          currency: 'sats',
          allow_fiat: false,
          fiat_currency: 'GBP',
          extra: {
            conditional: false,
            min_tickets: 1,
            email_notifications: false,
            nostr_notifications: false,
            promo_codes: [],
            notification_subject: '',
            notification_body: '',
            payment_methods: [],
            ln_wallet_id: null,
            onchain_wallet_id: null,
            fiat_provider: ''
          }
        }
        this.paymentMethods.ln = false
        this.paymentMethods.onchain = false
        this.paymentMethods.fiat = false
      }
      this.formDialog.show = true
    },
    resetEventDialog() {
      this.formDialog.show = false
      this.formDialog.data = {
        wallet: this.g.user.wallets?.[0]?.id,
        currency: 'sats',
        allow_fiat: false,
        fiat_currency: 'GBP',
        extra: {
          conditional: false,
          min_tickets: 1,
          email_notifications: false,
          nostr_notifications: false,
          promo_codes: [],
          notification_subject: '',
          notification_body: '',
          payment_methods: [],
          ln_wallet_id: null,
          onchain_wallet_id: null,
          fiat_provider: ''
        }
      }
      this.paymentMethods.ln = false
      this.paymentMethods.onchain = false
      this.paymentMethods.fiat = false
    },
    createEvent(wallet, data) {
      LNbits.api
        .request('POST', '/events/api/v1/events', wallet.adminkey, data)
        .then(response => {
          this.events.push(response.data)
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
          this.events.push(response.data)
          this.resetEventDialog()
        })
        .catch(LNbits.utils.notifyApiError)
    },
    deleteEvent(eventsId) {
      const events = _.findWhere(this.events, {id: eventsId})

      LNbits.utils
        .confirmDialog(this.$t('events.delete_event_confirm'))
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
            .catch(LNbits.utils.notifyApiError)
        })
    },
    exporteventsCSV() {
      LNbits.utils.exportCSV(this.eventsColumns, this.events)
    },
    async checkCanceledEvents() {
      const events = this.events
        .filter(event => event.extra.conditional)
        .filter(e => !e.canceled)
      if (!events.length) return
      const now = new Date()
      events.forEach(async ev => {
        if (new Date(ev.event_end_date) < now && ev.sold < ev.extra.min_tickets) {
          const {data} = await LNbits.api.request(
            'PUT',
            '/events/api/v1/events/' + ev.id + '/cancel',
            _.findWhere(this.g.user.wallets, {id: ev.wallet}).adminkey
          )
          Quasar.Notify.create({
            type: 'warning',
            message: this.$t('events.event_canceled_notify', {name: ev.name}),
            icon: null
          })
          this.events = this.events.map(e => (e.id === ev.id ? data : e))
        }
      })
    },

    loadTicketTypes(eventId) {
      const wallet = _.findWhere(this.g.user.wallets, {
        id: _.findWhere(this.events, {id: eventId})?.wallet
      })
      if (!wallet) return
      LNbits.api
        .request(
          'GET',
          `/events/api/v1/ticket-types/${eventId}`,
          wallet.inkey
        )
        .then(response => {
          this.ticketTypesByEvent[eventId] = response.data
        })
        .catch(LNbits.utils.notifyApiError)
    },
    openTicketTypeDialog(eventId, tt = null) {
      const event = _.findWhere(this.events, {id: eventId})
      if (!event) return
      const isEdit = Boolean(tt)
      this.ticketTypeDialog = {
        show: true,
        eventId,
        isEdit,
        wallet: event.wallet,
        data: {
          id: tt?.id || null,
          name: tt?.name || '',
          description: tt?.description || '',
          image_url: tt?.image_url || null,
          price: tt?.price || 0,
          max_tickets: tt?.max_tickets || 0,
          available_from:
            tt?.available_from || new Date().toISOString().slice(0, 10),
          available_to: tt?.available_to || event.event_end_date || '',
          sort_order: tt?.sort_order || 0,
          active: tt?.extra?.active ?? true,
          show_remaining: tt?.extra?.show_remaining ?? false,
          remaining_threshold: tt?.extra?.remaining_threshold ?? 0
        }
      }
    },
    resetTicketTypeDialog() {
      this.ticketTypeDialog = {
        show: false,
        eventId: null,
        isEdit: false,
        wallet: null,
        data: {
          id: null,
          name: '',
          description: '',
          image_url: null,
          price: 0,
          max_tickets: 0,
          available_from: '',
          available_to: '',
          sort_order: 0,
          active: true
        }
      }
    },
    saveTicketType() {
      const event = _.findWhere(this.events, {
        id: this.ticketTypeDialog.eventId
      })
      const wallet = _.findWhere(this.g.user.wallets, {
        id: this.ticketTypeDialog.wallet
      })
      if (!event || !wallet) return

      const payload = {
        ...this.ticketTypeDialog.data,
        event_id: this.ticketTypeDialog.eventId,
        extra: {
          ...this.ticketTypeDialog.data.extra,
          active: this.ticketTypeDialog.data.active,
          show_remaining: this.ticketTypeDialog.data.show_remaining,
          remaining_threshold: this.ticketTypeDialog.data.remaining_threshold
        }
      }
      if (!this.ticketTypeDialog.isEdit) {
        delete payload.id
      }
      delete payload.active
      delete payload.show_remaining
      delete payload.remaining_threshold

      const request = this.ticketTypeDialog.isEdit
        ? LNbits.api.request(
            'PUT',
            `/events/api/v1/ticket-types/${this.ticketTypeDialog.eventId}/${this.ticketTypeDialog.data.id}`,
            wallet.adminkey,
            payload
          )
        : LNbits.api.request(
            'POST',
            `/events/api/v1/ticket-types/${this.ticketTypeDialog.eventId}`,
            wallet.adminkey,
            payload
          )

      request
        .then(response => {
          const tts = this.ticketTypesByEvent[this.ticketTypeDialog.eventId] || []
          if (this.ticketTypeDialog.isEdit) {
            this.ticketTypesByEvent[this.ticketTypeDialog.eventId] = tts.map(
              t => (t.id === response.data.id ? response.data : t)
            )
          } else {
            this.ticketTypesByEvent[this.ticketTypeDialog.eventId] = [
              ...tts,
              response.data
            ]
          }
          Quasar.Notify.create({
            type: 'positive',
            message: this.ticketTypeDialog.isEdit
              ? this.$t('events.ticket_type_updated')
              : this.$t('events.ticket_type_added'),
            icon: null
          })
          this.resetTicketTypeDialog()
        })
        .catch(LNbits.utils.notifyApiError)
    },
    deleteTicketType(eventId, ttId) {
      const wallet = _.findWhere(this.g.user.wallets, {
        id: _.findWhere(this.events, {id: eventId})?.wallet
      })
      if (!wallet) return
      LNbits.utils
        .confirmDialog(this.$t('events.delete_ticket_type_confirm'))
        .onOk(() => {
          LNbits.api
            .request(
              'DELETE',
              `/events/api/v1/ticket-types/${eventId}/${ttId}`,
              wallet.adminkey
            )
            .then(() => {
              const tts = this.ticketTypesByEvent[eventId] || []
              this.ticketTypesByEvent[eventId] = tts.filter(
                t => t.id !== ttId
              )
              Quasar.Notify.create({
                type: 'positive',
                message: this.$t('events.ticket_type_deleted'),
                icon: null
              })
            })
            .catch(LNbits.utils.notifyApiError)
        })
    },
    openPromoCodesDialog(event) {
      // Normalise every promo onto the source axis and give the list's
      // q-selects real arrays to bind to (they default to null on the wire).
      const codes = (event.extra?.promo_codes || []).map(code => {
        const {type: _legacyType, ...rest} = code
        const source = this.normalizePromoSource(code)
        return {
          ...rest,
          source: {
            require_ticket: source.require_ticket,
            event_ids: source.event_ids || [],
            ticket_type_ids: source.ticket_type_ids || [],
            move: source.move,
            credit: source.credit
          },
          ticket_type_ids: [...(code.ticket_type_ids || [])]
        }
      })
      this.promoCodesDialog.data = {
        ...event,
        extra: {
          ...event.extra,
          promo_codes: codes
        }
      }
      this.promoDiscountTypes = {}
      codes.forEach((code, idx) => {
        this.promoDiscountTypes[idx] =
          code.discount_fixed != null ? 'fixed' : 'percent'
      })
      this.loadPromoScopeTicketTypes(codes, event.id)
      this.promoCodesDialog.show = true
    },
    resetPromoCodesDialog() {
      this.promoCodesDialog.show = false
      this.promoCodesDialog.data = {
        id: null,
        wallet: null,
        name: '',
        extra: {
          promo_codes: []
        }
      }
      this.promoDiscountTypes = {}
    },
    addPromoCodeToDialog() {
      const idx = this.promoCodesDialog.data.extra.promo_codes.length
      this.promoCodesDialog.data.extra.promo_codes.push({
        code: '',
        source: {
          require_ticket: false,
          event_ids: [],
          ticket_type_ids: [],
          move: false,
          credit: 'none'
        },
        discount_percent: undefined,
        discount_fixed: undefined,
        active: true,
        combinable: true,
        max_uses: null,
        used_count: 0,
        redemptions_per_ticket: 1,
        ticket_type_ids: [],
        max_tickets: null
      })
      this.promoDiscountTypes[idx] = 'percent'
    },
    onPromoDiscountTypeChange(index, type) {
      this.promoDiscountTypes[index] = type
      const code = this.promoCodesDialog.data.extra.promo_codes[index]
      if (!code) return
      if (type === 'fixed') {
        code.discount_percent = undefined
      } else {
        code.discount_fixed = undefined
      }
    },
    savePromoCodes() {
      const data = this.promoCodesDialog.data
      const wallet = _.findWhere(this.g.user.wallets, {
        id: data.wallet
      })
      if (!wallet) return

      const payload = {
        ...data,
        extra: {
          ...data.extra,
          promo_codes: this.normalizePromoCodes(data.extra?.promo_codes || [])
        }
      }

      LNbits.api
        .request(
          'PUT',
          '/events/api/v1/events/' + data.id,
          wallet.adminkey,
          payload
        )
        .then(response => {
          this.events = this.events.map(event =>
            event.id === data.id ? response.data : event
          )
          Quasar.Notify.create({
            type: 'positive',
            message: this.$t('events.promo_codes_updated'),
            icon: null
          })
          this.resetPromoCodesDialog()
        })
        .catch(LNbits.utils.notifyApiError)
    },
    openEditPromoCodeDialog(eventId, codeIndex) {
      const event = _.findWhere(this.events, {id: eventId})
      if (!event) return
      const code = event.extra?.promo_codes?.[codeIndex]
      if (!code) return
      this.editPromoCodeDialog.eventId = eventId
      this.editPromoCodeDialog.codeIndex = codeIndex
      // Drop the retired `type` axis and hand the dialog a `source` object
      // whose list fields are real arrays, which is what q-select needs.
      const {type: _legacyType, ...rest} = code
      const source = this.normalizePromoSource(code)
      this.editPromoCodeDialog.data = {
        ...rest,
        source: {
          require_ticket: source.require_ticket,
          event_ids: source.event_ids || [],
          ticket_type_ids: source.ticket_type_ids || [],
          move: source.move,
          credit: source.credit
        },
        ticket_type_ids: [...(code.ticket_type_ids || [])],
        max_uses: code.max_uses ?? null,
        max_tickets: code.max_tickets ?? null,
        redemptions_per_ticket: code.redemptions_per_ticket ?? 1
      }
      this.editPromoCodeDialog.discountType =
        code.discount_fixed != null ? 'fixed' : 'percent'
      if (!this.ticketTypesByEvent?.[eventId]) {
        this.loadTicketTypes(eventId)
      }
      this.loadPromoScopeTicketTypes([this.editPromoCodeDialog.data], eventId)
      this.editPromoCodeDialog.show = true
    },
    openAddPromoCodeDialog(eventId) {
      this.editPromoCodeDialog.eventId = eventId
      this.editPromoCodeDialog.codeIndex = -1
      this.editPromoCodeDialog.data = {
        code: '',
        source: {
          require_ticket: false,
          event_ids: [],
          ticket_type_ids: [],
          move: false,
          credit: 'none'
        },
        discount_percent: null,
        discount_fixed: null,
        active: true,
        combinable: true,
        max_uses: null,
        used_count: 0,
        redemptions_per_ticket: 1,
        ticket_type_ids: [],
        max_tickets: null
      }
      this.editPromoCodeDialog.discountType = 'percent'
      if (!this.ticketTypesByEvent?.[eventId]) {
        this.loadTicketTypes(eventId)
      }
      this.editPromoCodeDialog.show = true
    },
    onPromoRequireTicketChange(requireTicket) {
      const data = this.editPromoCodeDialog?.data
      if (!data) return
      if (!requireTicket) {
        // The ticket-only settings are meaningless without a ticket, and the
        // backend drops them anyway — clear them so the form matches what will
        // be saved. The offer code is NOT blanked: it identifies the offer and
        // is required when no ticket is involved.
        data.source.move = false
        data.source.credit = 'none'
        data.source.event_ids = []
        data.source.ticket_type_ids = []
      }
      // max_uses is deliberately left alone in both directions: a ticket rule
      // can cap its own usage now ("first 20 upgrades").
      this.loadPromoScopeTicketTypes(
        [data],
        this.editPromoCodeDialog?.eventId
      )
    },
    onPromoMoveChange(move) {
      const data = this.editPromoCodeDialog?.data
      if (!data) return
      if (move) {
        // "Move my ticket" is strictly one ticket in, one ticket out.
        data.max_tickets = null
      }
    },
    saveEditPromoCode() {
      const {eventId, codeIndex, data, discountType} = this.editPromoCodeDialog
      const event = _.findWhere(this.events, {id: eventId})
      if (!event) return
      const wallet = _.findWhere(this.g.user.wallets, {id: event.wallet})
      if (!wallet) return

      const source = this.normalizePromoSource(data)
      const code = {...data, source}
      delete code.type
      if (discountType === 'fixed') {
        code.discount_percent = null
      } else {
        code.discount_fixed = null
      }
      if (source.move) {
        // "Move my ticket" is strictly one ticket in, one ticket out.
        code.max_tickets = null
      }
      const scope = Array.isArray(code.ticket_type_ids)
        ? code.ticket_type_ids.filter(Boolean)
        : []
      code.ticket_type_ids = scope.length ? scope : null
      if (!code.max_tickets) code.max_tickets = null
      code.code = (code.code || '').trim().toUpperCase()

      // Without a ticket requirement the code is the only way in, so it cannot
      // be blank. With a ticket requirement a blank code is legitimate: the
      // rule is then activated by any eligible ticket id.
      if (!source.require_ticket && !code.code) {
        Quasar.Notify.create({
          type: 'negative',
          message: this.$t('events.promo_code_required'),
          icon: null
        })
        return
      }

      const codes = [...(event.extra?.promo_codes || [])]
      if (codeIndex >= 0 && codeIndex < codes.length) {
        codes[codeIndex] = code
      } else {
        codes.push(code)
      }

      const payload = {
        ...event,
        extra: {
          ...event.extra,
          promo_codes: codes
        }
      }

      LNbits.api
        .request('PUT', '/events/api/v1/events/' + eventId, wallet.adminkey, payload)
        .then(response => {
          this.events = this.events.map(e =>
            e.id === eventId ? response.data : e
          )
          Quasar.Notify.create({
            type: 'positive',
            message: this.$t('events.promo_codes_updated'),
            icon: null
          })
          this.editPromoCodeDialog.show = false
        })
        .catch(LNbits.utils.notifyApiError)
    },
    deletePromoCode(eventId, codeIndex) {
      const event = _.findWhere(this.events, {id: eventId})
      if (!event) return
      const wallet = _.findWhere(this.g.user.wallets, {id: event.wallet})
      if (!wallet) return

      const codes = [...(event.extra?.promo_codes || [])]
      codes.splice(codeIndex, 1)

      const payload = {
        ...event,
        extra: {
          ...event.extra,
          promo_codes: codes
        }
      }

      LNbits.api
        .request('PUT', '/events/api/v1/events/' + eventId, wallet.adminkey, payload)
        .then(response => {
          this.events = this.events.map(e =>
            e.id === eventId ? response.data : e
          )
          Quasar.Notify.create({
            type: 'positive',
            message: this.$t('events.promo_codes_updated'),
            icon: null
          })
          this.editPromoCodeDialog.show = false
        })
        .catch(LNbits.utils.notifyApiError)
    },
    resendAllTicketEmails(eventId) {
      const event = _.findWhere(this.events, {id: eventId})
      if (!event) return
      const wallet = _.findWhere(this.g.user.wallets, {id: event.wallet})
      if (!wallet) return

      Quasar.Dialog.create({
        title: this.$t('events.resend_all_emails'),
        message: this.$t('events.confirm_resend_all'),
        cancel: true,
        persistent: true
      }).onOk(() => {
        this.resendingAllEmailsFor.push(eventId)
        LNbits.api
          .request(
            'POST',
            `/events/api/v1/events/${eventId}/email-tickets`,
            wallet.adminkey,
            null
          )
          .then(response => {
            Quasar.Notify.create({
              type: 'positive',
              message: this.$t('events.bulk_email_sent'),
              icon: null
            })
          })
          .catch(LNbits.utils.notifyApiError)
          .finally(() => {
            this.resendingAllEmailsFor = this.resendingAllEmailsFor.filter(
              id => id !== eventId
            )
          })
      })
    },
    openEmailAllDialog(eventId) {
      this.emailAllDialog = {
        show: true,
        eventId,
        subject: '',
        message: '',
        loading: false
      }
    },
    resetEmailAllDialog() {
      this.emailAllDialog = {
        show: false,
        eventId: null,
        subject: '',
        message: '',
        loading: false
      }
    },
    sendEmailToAttendees() {
      if (!this.emailAllDialog.subject || !this.emailAllDialog.message) return
      const event = _.findWhere(this.events, {id: this.emailAllDialog.eventId})
      if (!event) return
      const wallet = _.findWhere(this.g.user.wallets, {id: event.wallet})
      if (!wallet) return

      this.emailAllDialog.loading = true
      LNbits.api
        .request(
          'POST',
          `/events/api/v1/events/${this.emailAllDialog.eventId}/email-message`,
          wallet.adminkey,
          {
            subject: this.emailAllDialog.subject,
            message: this.emailAllDialog.message
          }
        )
        .then(() => {
          Quasar.Notify.create({
            type: 'positive',
            message: this.$t('events.bulk_message_sent'),
            icon: null
          })
          this.resetEmailAllDialog()
        })
        .catch(LNbits.utils.notifyApiError)
        .finally(() => {
          this.emailAllDialog.loading = false
        })
    },
    previewTicketEmailUrl(event) {
      const wallet = _.findWhere(this.g.user.wallets, {id: event.wallet})
      if (!wallet) return '#'
      return `/events/api/v1/events/${event.id}/preview/ticket-email?key=${wallet.inkey}`
    },
    previewAdminEmailUrl(event) {
      const wallet = _.findWhere(this.g.user.wallets, {id: event.wallet})
      if (!wallet) return '#'
      return `/events/api/v1/events/${event.id}/preview/admin-email?key=${wallet.inkey}`
    }
  },
  created() {
    if (this.g.user.wallets.length) {
      this.getTickets()
      this.getAllTickets()
      this.getEvents()
      this.fetchWatchOnlyWallets()
      if (this.g.allowedCurrencies && this.g.allowedCurrencies.length > 0) {
        this.currencies = ['sats', ...this.g.allowedCurrencies]
      } else {
        this.currencies = ['sats', ...this.g.currencies]
      }
    }
  },
}
