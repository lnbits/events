window.PageEvents = {
  template: '#page-events',
  data() {
    return {
      events: [],
      tickets: [],
      resendingTicketEmails: [],
      isUploadingTicketTemplate: false,
      ticketImageUploadTarget: null,
      currencies: [],
      eventsTable: {
        columns: [
          {
            name: 'id',
            align: 'left',
            label: 'ID',
            field: row => this.shortenId(row.id)
          },
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
            name: 'canceled',
            align: 'left',
            label: 'Canceled',
            field: row => {
              if (row.extra.conditional && row.canceled) {
                return 'Yes'
              }
              return 'No'
            }
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      ticketsTable: {
        columns: [
          {
            name: 'event',
            align: 'left',
            label: 'Event',
            field: row => this.shortenId(row.event)
          },
          {name: 'name', align: 'left', label: 'Name', field: 'name'},
          {name: 'email', align: 'left', label: 'Email', field: 'email'},
          {
            name: 'registered',
            align: 'left',
            label: 'Registered',
            field: 'registered'
          },
          {
            name: 'nostr',
            align: 'left',
            label: 'Nostr',
            field: row => row.extra?.nostr_identifier || ''
          },
          {
            name: 'promo_code',
            align: 'left',
            label: 'Promo Code',
            field: row => row.extra.applied_promo_code || ''
          },
          {name: 'id', align: 'left', label: 'ID', field: 'id'}
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      formDialog: {
        show: false,
        data: {
          currency: 'sats',
          allow_fiat: false,
          fiat_currency: 'GBP',
          extra: {
            ticket_waves: [],
            promo_codes: [],
            notification_subject: '',
            notification_body: ''
          }
        }
      },
      ticketWaveDialog: {
        show: false,
        eventId: null,
        wallet: null,
        editingWaveId: null,
        data: {
          id: null,
          title: '',
          opening_date: '',
          closing_date: '',
          currency: 'sats',
          use_ticket_image: false,
          ticket_image_id: null,
          allow_fiat: false,
          fiat_currency: 'GBP',
          amount_tickets: 0,
          price_per_ticket: 0
        }
      },
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
      }
    }
  },
  methods: {
    shortenId(value) {
      if (!value) return ''
      return value.length > 4 ? `${value.slice(0, 4)}...` : value
    },
    primaryTicketWave(data = this.formDialog.data) {
      if (!data.extra) data.extra = {}
      if (!data.extra.ticket_waves || data.extra.ticket_waves.length === 0) {
        data.extra.ticket_waves = [
          {
            id: 'primary',
            title: 'Primary wave',
            opening_date: data.closing_date || '',
            closing_date: data.closing_date || '',
            currency: data.currency || 'sats',
            use_ticket_image: false,
            ticket_image_id: null,
            allow_fiat: Boolean(data.allow_fiat),
            fiat_currency: data.fiat_currency || 'GBP',
            amount_tickets: data.amount_tickets || 0,
            price_per_ticket: data.price_per_ticket || 0
          }
        ]
      }
      return data.extra.ticket_waves[0]
    },
    syncPrimaryWaveFromForm(data = this.formDialog.data) {
      const primaryWave = this.primaryTicketWave(data)
      primaryWave.title = primaryWave.title || 'Primary wave'
      primaryWave.opening_date = primaryWave.opening_date || ''
      primaryWave.closing_date = data.closing_date || ''
      primaryWave.currency = data.currency || 'sats'
      primaryWave.use_ticket_image = Boolean(primaryWave.use_ticket_image)
      primaryWave.ticket_image_id = primaryWave.ticket_image_id || null
      primaryWave.allow_fiat = Boolean(data.allow_fiat)
      primaryWave.fiat_currency = data.fiat_currency || 'GBP'
      primaryWave.amount_tickets = Number(data.amount_tickets || 0)
      primaryWave.price_per_ticket = Number(data.price_per_ticket || 0)
      return primaryWave
    },
    hydrateEventForm(data) {
      const formData = {
        ...data,
        extra: {
          ...(data.extra || {}),
          ticket_waves: [...((data.extra && data.extra.ticket_waves) || [])]
        }
      }
      const primaryWave = this.primaryTicketWave(formData)
      formData.currency = primaryWave.currency || formData.currency || 'sats'
      formData.allow_fiat = Boolean(primaryWave.allow_fiat)
      formData.fiat_currency = primaryWave.fiat_currency || 'GBP'
      formData.amount_tickets = primaryWave.amount_tickets
      formData.price_per_ticket = primaryWave.price_per_ticket
      formData.closing_date =
        primaryWave.closing_date || formData.closing_date || ''
      return formData
    },
    isFiatCurrency(currency) {
      return !['sat', 'sats'].includes((currency || '').toLowerCase())
    },
    normalizePromoCodes(promoCodes = []) {
      return promoCodes
        .filter(code => code.code?.trim() !== '')
        .map(code => ({
          ...code,
          code: code.code.trim().toUpperCase()
        }))
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
    triggerTicketImageUpload(target) {
      this.ticketImageUploadTarget = target
      this.$refs.ticketImageUpload.value = null
      this.$refs.ticketImageUpload.click()
    },
    async handleTicketImageSelected(event) {
      const file = event.target.files?.[0]
      if (!file || !this.ticketImageUploadTarget) return

      this.isUploadingTicketTemplate = true
      try {
        const assetId = await this.uploadAssetFile(file)
        if (this.ticketImageUploadTarget === 'primary') {
          const wave = this.primaryTicketWave()
          wave.use_ticket_image = true
          wave.ticket_image_id = assetId
        } else if (this.ticketImageUploadTarget === 'dialog') {
          this.ticketWaveDialog.data.use_ticket_image = true
          this.ticketWaveDialog.data.ticket_image_id = assetId
        }
        Quasar.Notify.create({
          type: 'positive',
          message: 'Ticket template uploaded.',
          icon: null
        })
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.isUploadingTicketTemplate = false
        this.ticketImageUploadTarget = null
      }
    },
    soldTicketsForWave(eventId, waveId) {
      return this.tickets.filter(
        ticket =>
          ticket.event === eventId &&
          ticket.paid &&
          (ticket.extra?.ticket_wave_id === waveId ||
            (!ticket.extra?.ticket_wave_id && waveId === 'primary'))
      ).length
    },
    getTickets() {
      LNbits.api
        .request(
          'GET',
          '/events/api/v1/tickets?all_wallets=true',
          this.g.user.wallets[0].adminkey
        )
        .then(response => {
          this.tickets = response.data.filter(e => e.paid)
        })
    },
    deleteTicket(ticketId) {
      const tickets = _.findWhere(this.tickets, {id: ticketId})
      const wallet = _.findWhere(this.g.user.wallets, {id: tickets.wallet})

      LNbits.utils
        .confirmDialog('Are you sure you want to delete this ticket')
        .onOk(() => {
          LNbits.api
            .request(
              'DELETE',
              '/events/api/v1/tickets/' + ticketId,
              wallet.adminkey
            )
            .then(response => {
              this.tickets = _.reject(this.tickets, function (obj) {
                return obj.id == ticketId
              })
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
                ? 'Ticket email resent.'
                : `Ticket email failed: ${result.email.error || 'Unknown error.'}`,
              icon: null
            })
          }

          if (result.nostr?.attempted) {
            Quasar.Notify.create({
              type: result.nostr.sent ? 'positive' : 'negative',
              message: result.nostr.sent
                ? 'Ticket Nostr DM resent.'
                : `Ticket Nostr DM failed: ${result.nostr.error || 'Unknown error.'}`,
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
          this.events = response.data
          this.checkCanceledEvents()
        })
    },
    sendEventData() {
      const wallet = _.findWhere(this.g.user.wallets, {
        id: this.formDialog.data.wallet
      })
      const data = this.formDialog.data
      this.syncPrimaryWaveFromForm(data)
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
      this.syncPrimaryWaveFromForm(data)

      if (data.id) {
        this.updateEvent(wallet, data)
      } else {
        this.createEvent(wallet, data)
      }
    },

    openEventDialog(data = false) {
      if (data && data.id) {
        this.formDialog.data = this.hydrateEventForm(data)
      } else {
        this.formDialog.data = {
          currency: 'sats',
          allow_fiat: false,
          fiat_currency: 'GBP',
          extra: {
            conditional: false,
            min_tickets: 1,
            email_notifications: false,
            nostr_notifications: false,
            ticket_waves: [
              {
                id: 'primary',
                title: 'Primary wave',
                opening_date: '',
                closing_date: '',
                currency: 'sats',
                use_ticket_image: false,
                ticket_image_id: null,
                allow_fiat: false,
                fiat_currency: 'GBP',
                amount_tickets: 0,
                price_per_ticket: 0
              }
            ],
            promo_codes: [],
            notification_subject: '',
            notification_body: ''
          }
        }
      }
      this.formDialog.show = true
    },
    resetEventDialog() {
      this.formDialog.show = false
      this.formDialog.data = {
        currency: 'sats',
        allow_fiat: false,
        fiat_currency: 'GBP',
        extra: {
          conditional: false,
          min_tickets: 1,
          email_notifications: false,
          nostr_notifications: false,
          ticket_waves: [
            {
              id: 'primary',
              title: 'Primary wave',
              opening_date: '',
              closing_date: '',
              currency: 'sats',
              use_ticket_image: false,
              ticket_image_id: null,
              allow_fiat: false,
              fiat_currency: 'GBP',
              amount_tickets: 0,
              price_per_ticket: 0
            }
          ],
          promo_codes: [],
          notification_subject: '',
          notification_body: ''
        }
      }
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
    openTicketWaveDialog(event, wave = null) {
      const primaryWave = (event.extra?.ticket_waves || [])[0] || {}
      const isEditing = Boolean(wave)
      this.ticketWaveDialog = {
        show: true,
        eventId: event.id,
        wallet: event.wallet,
        editingWaveId: wave?.id || null,
        data: {
          id: wave?.id || null,
          title: wave?.title || '',
          opening_date: wave?.opening_date || '',
          closing_date: wave?.closing_date || '',
          currency:
            wave?.currency || primaryWave.currency || event.currency || 'sats',
          use_ticket_image: Boolean(wave?.use_ticket_image),
          ticket_image_id: wave?.ticket_image_id || null,
          allow_fiat: isEditing
            ? Boolean(wave?.allow_fiat)
            : Boolean(primaryWave.allow_fiat ?? event.allow_fiat),
          fiat_currency:
            wave?.fiat_currency ||
            primaryWave.fiat_currency ||
            event.fiat_currency ||
            'GBP',
          amount_tickets: wave?.amount_tickets || 0,
          price_per_ticket:
            wave?.price_per_ticket ||
            primaryWave.price_per_ticket ||
            event.price_per_ticket ||
            0
        }
      }
    },
    resetTicketWaveDialog() {
      this.ticketWaveDialog = {
        show: false,
        eventId: null,
        wallet: null,
        editingWaveId: null,
        data: {
          id: null,
          title: '',
          opening_date: '',
          closing_date: '',
          currency: 'sats',
          use_ticket_image: false,
          ticket_image_id: null,
          allow_fiat: false,
          fiat_currency: 'GBP',
          amount_tickets: 0,
          price_per_ticket: 0
        }
      }
    },
    saveTicketWave() {
      const event = _.findWhere(this.events, {
        id: this.ticketWaveDialog.eventId
      })
      const wallet = _.findWhere(this.g.user.wallets, {
        id: this.ticketWaveDialog.wallet
      })
      if (!event || !wallet) return

      const payload = {
        ...event,
        extra: {
          ...event.extra,
          ticket_waves: (event.extra?.ticket_waves || []).map(existingWave =>
            existingWave.id === this.ticketWaveDialog.editingWaveId
              ? {...this.ticketWaveDialog.data}
              : existingWave
          )
        }
      }

      if (!this.ticketWaveDialog.editingWaveId) {
        payload.extra.ticket_waves.push({...this.ticketWaveDialog.data})
      }

      if (payload.extra?.promo_codes) {
        payload.extra.promo_codes = this.normalizePromoCodes(
          payload.extra.promo_codes
        )
      }

      LNbits.api
        .request(
          'PUT',
          '/events/api/v1/events/' + payload.id,
          wallet.adminkey,
          payload
        )
        .then(response => {
          this.events = this.events.map(item =>
            item.id === payload.id ? response.data : item
          )
          Quasar.Notify.create({
            type: 'positive',
            message: this.ticketWaveDialog.editingWaveId
              ? 'Ticket wave updated.'
              : 'Ticket wave added.',
            icon: null
          })
          this.resetTicketWaveDialog()
        })
        .catch(LNbits.utils.notifyApiError)
    },
    openPromoCodesDialog(event) {
      this.promoCodesDialog.data = {
        ...event,
        extra: {
          ...event.extra,
          promo_codes: [...(event.extra?.promo_codes || [])]
        }
      }
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
    },
    addPromoCodeToDialog() {
      this.promoCodesDialog.data.extra.promo_codes.push({
        code: '',
        discount_percent: 0,
        active: true
      })
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
            message: 'Promo codes updated.',
            icon: null
          })
          this.resetPromoCodesDialog()
        })
        .catch(LNbits.utils.notifyApiError)
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
            .catch(LNbits.utils.notifyApiError)
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
          this.events = this.events.map(e => (e.id === ev.id ? data : e))
        }
      })
    }
  },
  async created() {
    if (this.g.user.wallets.length) {
      this.getTickets()
      this.getEvents()
      if (this.g.allowedCurrencies && this.g.allowedCurrencies.length > 0) {
        this.currencies = ['sats', ...this.g.allowedCurrencies]
      } else {
        this.currencies = ['sats', ...this.g.currencies]
      }
    }
  }
}
