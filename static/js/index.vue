<template id="page-events">
  <div class="row q-col-gutter-md">
    <div class="col-12 col-md-8 col-lg-7 q-gutter-y-md">
      <q-card>
        <q-card-section>
          <q-btn unelevated color="primary" @click="openEventDialog"
            >New Event</q-btn
          >
        </q-card-section>
      </q-card>

      <q-card>
        <q-card-section>
          <div class="row items-center no-wrap q-mb-md">
            <div class="col">
              <h5 class="text-subtitle1 q-my-none">Events</h5>
            </div>
            <div class="col-auto">
              <q-btn flat color="grey" @click="exporteventsCSV"
                >Export to CSV</q-btn
              >
            </div>
          </div>
          <q-table
            dense
            flat
            :rows="events"
            row-key="id"
            :columns="eventsTable.columns"
            v-model:pagination="eventsTable.pagination"
          >
            <template v-slot:header="props">
              <q-tr :props="props">
                <q-th auto-width></q-th>
                <q-th auto-width></q-th>
                <q-th auto-width></q-th>
                <q-th v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.label"></span>
                </q-th>
              </q-tr>
            </template>
            <template v-slot:body="props">
              <q-tr :props="props">
                <q-td auto-width>
                  <q-btn
                    size="sm"
                    color="accent"
                    round
                    dense
                    @click="props.expand = !props.expand"
                    :icon="props.expand ? 'expand_less' : 'expand_more'"
                  />
                </q-td>
                <q-td auto-width>
                  <q-btn
                    unelevated
                    dense
                    size="xs"
                    icon="link"
                    :color="$q.dark.isActive ? 'grey-7' : 'grey-5'"
                    type="a"
                    :href="'/events/' + props.row.id"
                    target="_blank"
                  ></q-btn>
                  <q-btn
                    unelevated
                    dense
                    size="xs"
                    icon="how_to_reg"
                    :color="$q.dark.isActive ? 'grey-7' : 'grey-5'"
                    type="a"
                    :href="'/events/register/' + props.row.id"
                    target="_blank"
                    class="q-ml-xs"
                  ></q-btn>
                </q-td>
                <q-td auto-width>
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="updateformDialog(props.row.id)"
                    icon="edit"
                    color="light-blue"
                  ></q-btn>
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="deleteEvent(props.row.id)"
                    icon="cancel"
                    color="pink"
                    class="q-ml-xs"
                  ></q-btn>
                </q-td>
                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.value"></span>
                </q-td>
              </q-tr>
              <q-tr v-show="props.expand" :props="props">
                <q-td colspan="100%">
                  <div class="q-pa-md">
                    <div class="row items-center q-mb-md">
                      <div class="text-subtitle1">Ticket waves</div>
                      <q-btn
                        round
                        dense
                        unelevated
                        color="primary"
                        icon="add"
                        class="q-ml-sm"
                        @click="openTicketWaveDialog(props.row)"
                      ></q-btn>
                    </div>
                    <div class="column q-mb-lg">
                      <div class="column">
                        <div
                          v-for="(wave, index) in props.row.extra.ticket_waves"
                          :key="wave.id || index"
                          class="q-mb-sm"
                        >
                          <q-chip
                            square
                            clickable
                            class="q-py-xs"
                            style="height: auto"
                            @click="openTicketWaveDialog(props.row, wave)"
                          >
                            <span
                              style="white-space: normal; line-height: 1.3"
                              v-text="
                                `${wave.title} - ${wave.opening_date} to ${
                                  wave.closing_date
                                } - ${
                                  isFiatCurrency(wave.currency)
                                    ? LNbits.utils.formatCurrency(
                                        Number(
                                          wave.price_per_ticket || 0
                                        ).toFixed(2),
                                        wave.currency
                                      )
                                    : `${wave.price_per_ticket} sats`
                                } - ${wave.amount_tickets} tickets - ${soldTicketsForWave(
                                  props.row.id,
                                  wave.id
                                )} sold`
                              "
                            ></span>
                          </q-chip>
                        </div>
                      </div>
                    </div>

                    <div class="row items-center q-mb-md">
                      <div class="text-subtitle1">Promo codes</div>
                      <q-btn
                        round
                        dense
                        unelevated
                        color="primary"
                        icon="edit"
                        class="q-ml-sm"
                        @click="openPromoCodesDialog(props.row)"
                      ></q-btn>
                    </div>
                    <div class="column">
                      <div
                        v-if="
                          props.row.extra.promo_codes.filter(
                            code => code.active
                          ).length == 0
                        "
                        class="text-caption"
                      >
                        No active promo codes for this event.
                      </div>
                      <div class="row q-col-gutter-sm">
                        <div
                          v-for="(
                            code, index
                          ) in props.row.extra.promo_codes.filter(
                            code => code.active
                          )"
                          :key="index"
                          class="col-auto q-mb-sm"
                        >
                          <q-chip
                            square
                            clickable
                            @click="utils.copyText(code.code.toUpperCase())"
                          >
                            <span
                              v-text="
                                `${code.code.toUpperCase()} - ${code.discount_percent}%`
                              "
                            ></span>
                          </q-chip>
                        </div>
                      </div>
                    </div>
                  </div>
                </q-td>
              </q-tr>
            </template>
          </q-table>
        </q-card-section>
      </q-card>

      <q-card>
        <q-card-section>
          <div class="row items-center no-wrap q-mb-md">
            <div class="col">
              <h5 class="text-subtitle1 q-my-none">Tickets</h5>
            </div>
            <div class="col-auto">
              <q-btn flat color="grey" @click="exportticketsCSV"
                >Export to CSV</q-btn
              >
            </div>
          </div>
          <q-table
            dense
            flat
            :rows="tickets"
            :loading="ticketsTable.loading"
            row-key="id"
            :columns="ticketsTable.columns"
            v-model:pagination="ticketsTable.pagination"
            @request="getTickets"
          >
            <template v-slot:header="props">
              <q-tr :props="props">
                <q-th auto-width></q-th>
                <q-th auto-width></q-th>
                <q-th v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.label"></span>
                </q-th>
                <q-th auto-width></q-th>
              </q-tr>
            </template>
            <template v-slot:body="props">
              <q-tr :props="props">
                <q-td auto-width>
                  <q-btn
                    unelevated
                    dense
                    size="xs"
                    icon="local_activity"
                    :color="$q.dark.isActive ? 'grey-7' : 'grey-5'"
                    type="a"
                    :href="'/events/ticket/' + props.row.id"
                    target="_blank"
                  ></q-btn>
                </q-td>
                <q-td auto-width>
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="resendTicketEmail(props.row)"
                    icon="email"
                    color="primary"
                    :disable="!props.row.paid || !props.row.email"
                    :loading="resendingTicketEmails.includes(props.row.id)"
                  >
                    <q-tooltip>Resend ticket email</q-tooltip>
                  </q-btn>
                  <q-btn
                    v-if="props.row.extra?.onchain && !props.row.paid"
                    flat
                    dense
                    size="xs"
                    @click="confirmOnchainTicket(props.row)"
                    icon="currency_bitcoin"
                    color="orange"
                    class="q-ml-xs"
                  >
                    <q-tooltip>Confirm onchain payment</q-tooltip>
                  </q-btn>
                </q-td>

                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.value"></span>
                </q-td>

                <q-td auto-width>
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="deleteTicket(props.row.id)"
                    icon="cancel"
                    color="pink"
                  ></q-btn>
                </q-td>
              </q-tr>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </div>
    <div class="col-12 col-md-4 col-lg-5 q-gutter-y-md">
      <q-card>
        <q-card-section>
          <h6 class="text-subtitle1 ellipsis q-my-none">
            <span v-text="SITE_TITLE"></span>
            Events extension
          </h6>
        </q-card-section>
        <q-card-section class="q-pa-none">
          <q-separator></q-separator>
          <q-list>
            <q-expansion-item
              group="extras"
              icon="swap_vertical_circle"
              label="Info"
              :content-inset-level="0.5"
            >
              <q-card>
                <q-card-section>
                  <h5 class="text-subtitle1 q-my-none">
                    Events: Sell and register ticket waves for an event
                  </h5>
                  <p>
                    Events allows you to make a wave of tickets for an event,
                    each ticket is in the form of a unique QRcode, which the
                    user presents at registration. Events comes with a shareable
                    ticket scanner, which can be used to register attendees.<br />
                    <small>
                      Created by,
                      <a class="text-secondary" href="https://github.com/benarc"
                        >Ben Arc</a
                      >
                    </small>
                  </p>
                </q-card-section>
              </q-card>
              <q-btn
                flat
                label="Swagger API"
                type="a"
                href="../docs#/events"
              ></q-btn>
            </q-expansion-item>
          </q-list>
        </q-card-section>
      </q-card>
    </div>

    <q-dialog v-model="formDialog.show" position="top">
      <q-card class="q-pa-lg q-pt-xl lnbits__dialog-card">
        <q-form @submit="sendEventData" class="q-gutter-md">
          <div class="row">
            <div class="col">
              <q-input
                filled
                dense
                v-model.trim="formDialog.data.name"
                type="name"
                label="Title of event "
              ></q-input>
            </div>
            <div class="col q-pl-sm">
              <q-select
                filled
                dense
                emit-value
                v-model="formDialog.data.wallet"
                :options="g.user.walletOptions"
                label="Wallet *"
              >
              </q-select>
            </div>
          </div>

          <q-input
            filled
            dense
            v-model.trim="formDialog.data.info"
            type="textarea"
            label="Info about the event"
            hint="Markdown supported"
          ></q-input>
          <q-input
            filled
            dense
            v-model.trim="formDialog.data.banner"
            type="url"
            label="Image URL"
            hint="Optional banner image to display on the event page"
          ></q-input>
          <div class="row q-mt-lg">
            <div class="col-4">Event begins</div>
            <div class="col-8">
              <q-input
                filled
                dense
                v-model.trim="formDialog.data.event_start_date"
                type="date"
              ></q-input>
            </div>
          </div>
          <div class="row">
            <div class="col-4">Event ends</div>
            <div class="col-8">
              <q-input
                filled
                dense
                v-model.trim="formDialog.data.event_end_date"
                type="date"
              ></q-input>
            </div>
          </div>
          <q-separator class="q-my-md"></q-separator>
          <div class="text-subtitle1 q-mt-lg q-mb-md">
            Primary ticket wave (you can add other waves later)
          </div>
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="primaryTicketWave().title"
                type="text"
                label="Wave title"
              ></q-input>
            </div>
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="primaryTicketWave().opening_date"
                type="date"
                label="Ticket opening date"
              ></q-input>
            </div>
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="formDialog.data.closing_date"
                type="date"
                label="Ticket closing date"
              ></q-input>
            </div>
          </div>
          <div class="row q-col-gutter-sm">
            <div class="col">
              <q-select
                filled
                dense
                v-model="formDialog.data.currency"
                type="text"
                label="Unit"
                :options="currencies"
              ></q-select>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="formDialog.data.amount_tickets"
                type="number"
                label="Amount of tickets "
              ></q-input>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="formDialog.data.price_per_ticket"
                type="number"
                :label="'Price (' + formDialog.data.currency + ') *'"
                :step="formDialog.data.currency != 'sats' ? '0.01' : '1'"
                :mask="formDialog.data.currency != 'sats' ? '#.##' : '#'"
                fill-mask="0"
                reverse-fill-mask
                :disable="formDialog.data.currency == null"
              ></q-input>
            </div>
          </div>
          <q-toggle
            v-model="primaryTicketWave().use_ticket_image"
            label="Use ticket image"
            left-label
          ></q-toggle>
          <div
            v-if="primaryTicketWave().use_ticket_image"
            class="row items-center q-col-gutter-sm q-mb-sm"
          >
            <div class="col-auto">
              <q-btn
                unelevated
                color="primary"
                type="a"
                :href="templateDownloadUrl()"
                download="ticket.jpg"
              >
                Download template
                <q-tooltip>400/733 jpg</q-tooltip>
              </q-btn>
            </div>
            <div class="col-auto">
              <q-btn
                outline
                color="primary"
                :loading="isUploadingTicketTemplate"
                @click="triggerTicketImageUpload('primary')"
                >Replace</q-btn
              >
            </div>
            <div
              v-if="primaryTicketWave().ticket_image_id"
              class="col-12 text-caption"
            >
              Custom ticket template uploaded.
            </div>
          </div>
          <q-toggle
            v-model="formDialog.data.allow_fiat"
            label="Allow fiat checkout"
            left-label
            hint="Lets attendees pay through a configured fiat provider using the event currency."
          ></q-toggle>
          <q-select
            v-if="
              formDialog.data.allow_fiat &&
              ['sat', 'sats'].includes(
                (formDialog.data.currency || '').toLowerCase()
              )
            "
            filled
            dense
            v-model="formDialog.data.fiat_currency"
            label="Fiat checkout currency"
            :options="
              currencies.filter(
                c => !['sat', 'sats'].includes((c || '').toLowerCase())
              )
            "
          ></q-select>
          <q-expansion-item
            group="advanced"
            icon="settings"
            label="Advanced options"
          >
            <div class="row q-mt-lg">
              <div class="text-subtitle1 q-mb-md">Conditional Events</div>
              <div class="text-caption">
                Make this event conditional if
                <strong>minimum tickets</strong> are sold. User will be asked to
                provide a Lightning Address or LNURL pay for refunds.
              </div>
              <div class="col-8">
                <q-toggle
                  v-model="formDialog.data.extra.conditional"
                  label="Conditional Event"
                  left-label
                ></q-toggle>
              </div>
              <div class="col-4">
                <q-input
                  filled
                  dense
                  v-model.number="formDialog.data.extra.min_tickets"
                  type="number"
                  label="Minimum Tickets"
                  :disable="!formDialog.data.extra.conditional"
                ></q-input>
              </div>
            </div>
            <q-separator class="q-my-md"></q-separator>
            <div class="text-subtitle1 q-mb-md">Ticket Delivery</div>
            <div class="text-caption">
              Send the paid ticket link automatically by email or Nostr DM.
            </div>
            <div class="row items-center q-col-gutter-md">
              <div class="col-auto">
                <q-toggle
                  v-model="formDialog.data.extra.email_notifications"
                  label="Email notifications"
                  left-label
                ></q-toggle>
              </div>
              <div class="col-auto">
                <q-toggle
                  v-model="formDialog.data.extra.nostr_notifications"
                  label="Nostr notifications"
                  left-label
                ></q-toggle>
              </div>
            </div>
            <div
              v-if="formDialog.data.extra.email_notifications"
              class="q-mt-md"
            >
              <q-input
                filled
                dense
                v-model.trim="formDialog.data.extra.notification_subject"
                type="text"
                label="Ticket notification subject"
                hint="Used as the email subject when sending paid ticket links."
              ></q-input>
              <q-input
                class="q-mt-md"
                filled
                dense
                v-model.trim="formDialog.data.extra.notification_body"
                type="textarea"
                label="Ticket notification body"
                hint="Shown before the ticket link in the paid ticket notification."
              ></q-input>
            </div>
          </q-expansion-item>

          <q-expansion-item
            group="advanced"
            icon="view_in_ar"
            label="Onchain payments"
          >
            <div class="q-mt-lg">
              <div class="text-caption q-mb-md">
                Accept Bitcoin onchain payments. Requires the
                <strong>SatsPay</strong> and <strong>Watchonly</strong>
                extensions to be installed and enabled.
              </div>
              <q-toggle
                v-model="formDialog.data.extra.onchain_enabled"
                label="Accept onchain payments"
                left-label
                @update:model-value="val => val && loadOnchainWallets()"
              ></q-toggle>
              <q-select
                v-if="formDialog.data.extra.onchain_enabled"
                filled
                dense
                class="q-mt-md"
                v-model="formDialog.data.extra.onchain_wallet_id"
                label="Watchonly wallet"
                :options="
                  onchainWallets.map(w => ({
                    label: w.title || w.id,
                    value: w.id
                  }))
                "
                emit-value
                map-options
                hint="Bitcoin watchonly wallet for receiving onchain payments"
              ></q-select>
              <div v-if="formDialog.data.extra.onchain_enabled" class="q-mt-md">
                <q-toggle
                  v-model="formDialog.data.extra.onchain_zeroconf"
                  label="Zero-conf (accept unconfirmed transactions)"
                  left-label
                ></q-toggle>
                <q-toggle
                  v-model="formDialog.data.extra.onchain_fasttrack"
                  label="Fasttrack (treat pending as paid)"
                  left-label
                ></q-toggle>
              </div>
            </div>
          </q-expansion-item>

          <div class="row q-mt-lg">
            <q-btn
              v-if="formDialog.data.id"
              unelevated
              color="primary"
              type="submit"
              >Update Event</q-btn
            >
            <q-btn
              v-else
              unelevated
              color="primary"
              :disable="
                formDialog.data.wallet == null ||
                formDialog.data.name == null ||
                formDialog.data.info == null ||
                formDialog.data.closing_date == null ||
                primaryTicketWave().title == null ||
                primaryTicketWave().opening_date == null ||
                formDialog.data.event_start_date == null ||
                formDialog.data.event_end_date == null ||
                formDialog.data.amount_tickets == null ||
                formDialog.data.price_per_ticket == null
              "
              type="submit"
              >Create Event</q-btn
            >
            <q-btn v-close-popup flat color="grey" class="q-ml-auto"
              >Cancel</q-btn
            >
          </div>
        </q-form>
      </q-card>
    </q-dialog>

    <q-dialog v-model="promoCodesDialog.show" position="top">
      <q-card class="q-pa-lg q-pt-xl lnbits__dialog-card">
        <q-form @submit="savePromoCodes" class="q-gutter-md">
          <div class="text-subtitle1">Promo Codes</div>
          <div class="text-caption">
            Allow users to enter a promo code for discounts.
          </div>

          <div
            v-for="(code, index) in promoCodesDialog.data.extra.promo_codes"
            :key="index"
            class="row q-col-gutter-sm q-mt-md"
          >
            <q-input
              class="col-8"
              filled
              dense
              v-model.trim="promoCodesDialog.data.extra.promo_codes[index].code"
              type="text"
              label="Promo Code"
            >
              <template v-slot:before>
                <q-checkbox
                  left-label
                  v-model="
                    promoCodesDialog.data.extra.promo_codes[index].active
                  "
                  checked-icon="radio_button_checked"
                  unchecked-icon="radio_button_unchecked"
                ></q-checkbox>
                <q-tooltip>
                  <span
                    v-text="
                      promoCodesDialog.data.extra.promo_codes[index].active
                        ? 'Active'
                        : 'Inactive'
                    "
                  ></span>
                </q-tooltip>
              </template>
            </q-input>
            <q-input
              class="col-4"
              filled
              dense
              v-model.number="
                promoCodesDialog.data.extra.promo_codes[index].discount_percent
              "
              type="number"
              label="Discount (%)"
              min="0"
              max="100"
            >
              <template v-slot:after>
                <q-btn
                  round
                  dense
                  flat
                  icon="delete"
                  @click="
                    promoCodesDialog.data.extra.promo_codes.splice(index, 1)
                  "
                ></q-btn>
              </template>
            </q-input>
          </div>

          <div class="col-12 q-mt-md">
            <q-btn @click="addPromoCodeToDialog">Add Promo Code</q-btn>
          </div>

          <div class="row q-mt-lg">
            <q-btn unelevated color="primary" type="submit"
              >Save Promo Codes</q-btn
            >
            <q-btn
              flat
              color="grey"
              class="q-ml-auto"
              @click="resetPromoCodesDialog"
              >Cancel</q-btn
            >
          </div>
        </q-form>
      </q-card>
    </q-dialog>

    <q-dialog v-model="ticketWaveDialog.show" position="top">
      <q-card class="q-pa-lg q-pt-xl lnbits__dialog-card">
        <q-form @submit="saveTicketWave" class="q-gutter-md">
          <div
            class="text-subtitle1"
            v-text="
              ticketWaveDialog.editingWaveId
                ? 'Edit Ticket Wave'
                : 'Add Ticket Wave'
            "
          ></div>
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="ticketWaveDialog.data.title"
                type="text"
                label="Wave title"
              ></q-input>
            </div>
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="ticketWaveDialog.data.opening_date"
                type="date"
                label="Ticket opening date"
              ></q-input>
            </div>
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="ticketWaveDialog.data.closing_date"
                type="date"
                label="Ticket closing date"
              ></q-input>
            </div>
          </div>
          <div class="row q-col-gutter-sm">
            <div class="col">
              <q-select
                filled
                dense
                v-model="ticketWaveDialog.data.currency"
                type="text"
                label="Unit"
                :options="currencies"
              ></q-select>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="ticketWaveDialog.data.amount_tickets"
                type="number"
                label="Amount of tickets"
              ></q-input>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="ticketWaveDialog.data.price_per_ticket"
                type="number"
                :label="'Price (' + ticketWaveDialog.data.currency + ') *'"
                :step="ticketWaveDialog.data.currency != 'sats' ? '0.01' : '1'"
                :mask="ticketWaveDialog.data.currency != 'sats' ? '#.##' : '#'"
                fill-mask="0"
                reverse-fill-mask
                :disable="ticketWaveDialog.data.currency == null"
              ></q-input>
            </div>
          </div>
          <q-toggle
            v-model="ticketWaveDialog.data.use_ticket_image"
            label="Use ticket image"
            left-label
          ></q-toggle>
          <div
            v-if="ticketWaveDialog.data.use_ticket_image"
            class="row items-center q-col-gutter-sm q-mb-sm"
          >
            <div class="col-auto">
              <q-btn
                unelevated
                color="primary"
                type="a"
                :href="templateDownloadUrl()"
                download="ticket.jpg"
              >
                Download template
                <q-tooltip>400/733 jpg</q-tooltip>
              </q-btn>
            </div>
            <div class="col-auto">
              <q-btn
                outline
                color="primary"
                :loading="isUploadingTicketTemplate"
                @click="triggerTicketImageUpload('dialog')"
                >Replace</q-btn
              >
            </div>
            <div
              v-if="ticketWaveDialog.data.ticket_image_id"
              class="col-12 text-caption"
            >
              Custom ticket template uploaded.
            </div>
          </div>
          <q-toggle
            v-model="ticketWaveDialog.data.allow_fiat"
            label="Allow fiat checkout"
            left-label
            hint="Lets attendees pay through a configured fiat provider using this wave currency."
          ></q-toggle>
          <q-select
            v-if="
              ticketWaveDialog.data.allow_fiat &&
              ['sat', 'sats'].includes(
                (ticketWaveDialog.data.currency || '').toLowerCase()
              )
            "
            filled
            dense
            v-model="ticketWaveDialog.data.fiat_currency"
            label="Fiat checkout currency"
            :options="
              currencies.filter(
                c => !['sat', 'sats'].includes((c || '').toLowerCase())
              )
            "
          ></q-select>
          <div class="row q-mt-lg">
            <q-btn unelevated color="primary" type="submit">{{
              ticketWaveDialog.editingWaveId
                ? 'Update Ticket Wave'
                : 'Save Ticket Wave'
            }}</q-btn>
            <q-btn
              flat
              color="grey"
              class="q-ml-auto"
              @click="resetTicketWaveDialog"
              >Cancel</q-btn
            >
          </div>
        </q-form>
      </q-card>
    </q-dialog>
    <input
      ref="ticketImageUpload"
      type="file"
      accept="image/png,image/jpeg,image/webp"
      style="display: none"
      @change="handleTicketImageSelected"
    />
  </div>
</template>
