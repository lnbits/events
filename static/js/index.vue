<template id="page-events">
  <div class="row q-col-gutter-md">
    <div class="col-12 col-md-8 col-lg-7 q-gutter-y-md">
      <q-card>
        <q-card-section>
          <q-btn
            unelevated
            color="primary"
            :label="$t('events.new_event')"
            @click="openEventDialog"
          ></q-btn>
        </q-card-section>
      </q-card>

      <q-card>
        <q-card-section>
          <div class="row items-center no-wrap q-mb-md">
            <div class="col">
              <h5
                class="text-subtitle1 q-my-none"
                v-text="$t('events.events_title')"
              ></h5>
            </div>
            <div class="col-auto">
              <q-btn
                flat
                color="grey"
                @click="exporteventsCSV"
                v-text="$t('events.export_csv')"
              ></q-btn>
            </div>
          </div>
          <q-table
            dense
            flat
            :rows="events"
            row-key="id"
            :columns="eventsColumns"
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
                      <div
                        class="text-subtitle1"
                        v-text="$t('events.ticket_waves')"
                      ></div>
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
                              v-text="waveChipLabel(props.row, wave)"
                            ></span>
                          </q-chip>
                        </div>
                      </div>
                    </div>

                    <div class="row items-center q-mb-md">
                      <div
                        class="text-subtitle1"
                        v-text="$t('events.promo_codes')"
                      ></div>
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
                        v-text="$t('events.no_active_promo_codes')"
                      ></div>
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
              <h5
                class="text-subtitle1 q-my-none"
                v-text="$t('events.tickets_title')"
              ></h5>
            </div>
            <div class="col-auto">
              <q-btn
                flat
                color="grey"
                @click="exportticketsCSV"
                v-text="$t('events.export_csv')"
              ></q-btn>
            </div>
          </div>
          <q-table
            dense
            flat
            :rows="tickets"
            :loading="ticketsTable.loading"
            row-key="id"
            :columns="ticketsColumns"
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
                    <q-tooltip>
                      <span v-text="$t('events.resend_ticket_email')"></span>
                    </q-tooltip>
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
                    <q-tooltip>
                      <span
                        v-text="$t('events.confirm_onchain_payment')"
                      ></span>
                    </q-tooltip>
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
            <span v-text="' ' + $t('events.extension_title')"></span>
          </h6>
        </q-card-section>
        <q-card-section class="q-pa-none">
          <q-separator></q-separator>
          <q-list>
            <q-expansion-item
              group="extras"
              icon="swap_vertical_circle"
              :label="$t('events.info_label')"
              :content-inset-level="0.5"
            >
              <q-card>
                <q-card-section>
                  <h5
                    class="text-subtitle1 q-my-none"
                    v-text="$t('events.extension_desc_title')"
                  ></h5>
                  <p>
                    <span v-text="$t('events.extension_desc')"></span><br />
                    <small>
                      <span v-text="$t('events.created_by')"></span>
                      <a class="text-secondary" href="https://github.com/benarc"
                        >Ben Arc</a
                      >
                    </small>
                  </p>
                </q-card-section>
              </q-card>
              <q-btn
                flat
                :label="$t('events.swagger_api')"
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
                :label="$t('events.event_title_label')"
              ></q-input>
            </div>
            <div class="col q-pl-sm">
              <q-select
                filled
                dense
                emit-value
                v-model="formDialog.data.wallet"
                :options="g.user.walletOptions"
                :label="$t('events.wallet_label')"
              >
              </q-select>
            </div>
          </div>

          <q-input
            filled
            dense
            v-model.trim="formDialog.data.info"
            type="textarea"
            :label="$t('events.event_info_label')"
            :hint="$t('events.markdown_supported')"
          ></q-input>
          <q-input
            filled
            dense
            v-model.trim="formDialog.data.banner"
            type="url"
            :label="$t('events.image_url_label')"
            :hint="$t('events.image_url_hint')"
          ></q-input>
          <div class="row q-mt-lg">
            <div class="col-4" v-text="$t('events.event_begins')"></div>
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
            <div class="col-4" v-text="$t('events.event_ends')"></div>
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
          <div
            class="text-subtitle1 q-mt-lg q-mb-md"
            v-text="$t('events.primary_wave_hint')"
          ></div>
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="primaryTicketWave().title"
                type="text"
                :label="$t('events.wave_title_label')"
              ></q-input>
            </div>
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="primaryTicketWave().opening_date"
                type="date"
                :label="$t('events.opening_date_label')"
              ></q-input>
            </div>
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="formDialog.data.closing_date"
                type="date"
                :label="$t('events.closing_date_label')"
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
                :label="$t('events.unit_label')"
                :options="currencies"
              ></q-select>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="formDialog.data.amount_tickets"
                type="number"
                :label="$t('events.amount_tickets_label')"
              ></q-input>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="formDialog.data.price_per_ticket"
                type="number"
                :label="
                  $t('events.price_label', {currency: formDialog.data.currency})
                "
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
            :label="$t('events.use_ticket_image')"
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
                <span v-text="$t('events.download_template')"></span>
                <q-tooltip>400/733 jpg</q-tooltip>
              </q-btn>
            </div>
            <div class="col-auto">
              <q-btn
                outline
                color="primary"
                :loading="isUploadingTicketTemplate"
                @click="triggerTicketImageUpload('primary')"
                v-text="$t('events.replace_template')"
              ></q-btn>
            </div>
            <div
              v-if="primaryTicketWave().ticket_image_id"
              class="col-12 text-caption"
              v-text="$t('events.custom_template_uploaded')"
            ></div>
          </div>
          <q-toggle
            v-model="formDialog.data.allow_fiat"
            :label="$t('events.allow_fiat_checkout')"
            left-label
            :hint="$t('events.allow_fiat_hint')"
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
            :label="$t('events.fiat_checkout_currency')"
            :options="
              currencies.filter(
                c => !['sat', 'sats'].includes((c || '').toLowerCase())
              )
            "
          ></q-select>
          <q-expansion-item
            group="advanced"
            icon="settings"
            :label="$t('events.advanced_options')"
          >
            <div class="row q-mt-lg">
              <div
                class="text-subtitle1 q-mb-md"
                v-text="$t('events.conditional_events_title')"
              ></div>
              <div
                class="text-caption"
                v-text="$t('events.conditional_events_desc')"
              ></div>
              <div class="col-8">
                <q-toggle
                  v-model="formDialog.data.extra.conditional"
                  :label="$t('events.conditional_event_label')"
                  left-label
                ></q-toggle>
              </div>
              <div class="col-4">
                <q-input
                  filled
                  dense
                  v-model.number="formDialog.data.extra.min_tickets"
                  type="number"
                  :label="$t('events.min_tickets_label')"
                  :disable="!formDialog.data.extra.conditional"
                ></q-input>
              </div>
            </div>
            <q-separator class="q-my-md"></q-separator>
            <div
              class="text-subtitle1 q-mb-md"
              v-text="$t('events.ticket_delivery_title')"
            ></div>
            <div
              class="text-caption"
              v-text="$t('events.ticket_delivery_desc')"
            ></div>
            <div class="row items-center q-col-gutter-md">
              <div class="col-auto">
                <q-toggle
                  v-model="formDialog.data.extra.email_notifications"
                  :label="$t('events.email_notifications')"
                  left-label
                ></q-toggle>
              </div>
              <div class="col-auto">
                <q-toggle
                  v-model="formDialog.data.extra.nostr_notifications"
                  :label="$t('events.nostr_notifications')"
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
                :label="$t('events.notification_subject_label')"
                :hint="$t('events.notification_subject_hint')"
              ></q-input>
              <q-input
                class="q-mt-md"
                filled
                dense
                v-model.trim="formDialog.data.extra.notification_body"
                type="textarea"
                :label="$t('events.notification_body_label')"
                :hint="$t('events.notification_body_hint')"
              ></q-input>
            </div>
          </q-expansion-item>

          <q-expansion-item
            group="advanced"
            icon="view_in_ar"
            :label="$t('events.onchain_payments')"
          >
            <div class="q-mt-lg">
              <div
                class="text-caption q-mb-md"
                v-text="$t('events.onchain_desc')"
              ></div>
              <q-toggle
                v-model="formDialog.data.extra.onchain_enabled"
                :label="$t('events.accept_onchain')"
                left-label
                @update:model-value="val => val && loadOnchainWallets()"
              ></q-toggle>
              <q-select
                v-if="formDialog.data.extra.onchain_enabled"
                filled
                dense
                class="q-mt-md"
                v-model="formDialog.data.extra.onchain_wallet_id"
                :label="$t('events.watchonly_wallet')"
                :options="
                  onchainWallets.map(w => ({
                    label: w.title || w.id,
                    value: w.id
                  }))
                "
                emit-value
                map-options
                :hint="$t('events.watchonly_wallet_hint')"
              ></q-select>
              <div v-if="formDialog.data.extra.onchain_enabled" class="q-mt-md">
                <q-toggle
                  v-model="formDialog.data.extra.onchain_zeroconf"
                  :label="$t('events.onchain_zeroconf')"
                  left-label
                ></q-toggle>
                <q-toggle
                  v-model="formDialog.data.extra.onchain_fasttrack"
                  :label="$t('events.onchain_fasttrack')"
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
              v-text="$t('events.update_event')"
            ></q-btn>
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
              v-text="$t('events.create_event')"
            ></q-btn>
            <q-btn
              v-close-popup
              flat
              color="grey"
              class="q-ml-auto"
              v-text="$t('cancel')"
            ></q-btn>
          </div>
        </q-form>
      </q-card>
    </q-dialog>

    <q-dialog v-model="promoCodesDialog.show" position="top">
      <q-card class="q-pa-lg q-pt-xl lnbits__dialog-card">
        <q-form @submit="savePromoCodes" class="q-gutter-md">
          <div
            class="text-subtitle1"
            v-text="$t('events.promo_codes_title')"
          ></div>
          <div
            class="text-caption"
            v-text="$t('events.promo_codes_desc')"
          ></div>

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
              :label="$t('events.promo_code_label')"
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
                        ? $t('events.active')
                        : $t('events.inactive')
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
              :label="$t('events.discount_label')"
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
            <q-btn
              @click="addPromoCodeToDialog"
              v-text="$t('events.add_promo_code')"
            ></q-btn>
          </div>

          <div class="row q-mt-lg">
            <q-btn
              unelevated
              color="primary"
              type="submit"
              v-text="$t('events.save_promo_codes')"
            ></q-btn>
            <q-btn
              flat
              color="grey"
              class="q-ml-auto"
              @click="resetPromoCodesDialog"
              v-text="$t('cancel')"
            ></q-btn>
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
                ? $t('events.edit_ticket_wave')
                : $t('events.add_ticket_wave')
            "
          ></div>
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="ticketWaveDialog.data.title"
                type="text"
                :label="$t('events.wave_title_label')"
              ></q-input>
            </div>
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="ticketWaveDialog.data.opening_date"
                type="date"
                :label="$t('events.opening_date_label')"
              ></q-input>
            </div>
            <div class="col-12 col-md-4">
              <q-input
                filled
                dense
                v-model.trim="ticketWaveDialog.data.closing_date"
                type="date"
                :label="$t('events.closing_date_label')"
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
                :label="$t('events.unit_label')"
                :options="currencies"
              ></q-select>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="ticketWaveDialog.data.amount_tickets"
                type="number"
                :label="$t('events.amount_tickets_label')"
              ></q-input>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="ticketWaveDialog.data.price_per_ticket"
                type="number"
                :label="
                  $t('events.price_label', {
                    currency: ticketWaveDialog.data.currency
                  })
                "
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
            :label="$t('events.use_ticket_image')"
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
                <span v-text="$t('events.download_template')"></span>
                <q-tooltip>400/733 jpg</q-tooltip>
              </q-btn>
            </div>
            <div class="col-auto">
              <q-btn
                outline
                color="primary"
                :loading="isUploadingTicketTemplate"
                @click="triggerTicketImageUpload('dialog')"
                v-text="$t('events.replace_template')"
              ></q-btn>
            </div>
            <div
              v-if="ticketWaveDialog.data.ticket_image_id"
              class="col-12 text-caption"
              v-text="$t('events.custom_template_uploaded')"
            ></div>
          </div>
          <q-toggle
            v-model="ticketWaveDialog.data.allow_fiat"
            :label="$t('events.allow_fiat_checkout')"
            left-label
            :hint="$t('events.wave_allow_fiat_hint')"
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
            :label="$t('events.fiat_checkout_currency')"
            :options="
              currencies.filter(
                c => !['sat', 'sats'].includes((c || '').toLowerCase())
              )
            "
          ></q-select>
          <div class="row q-mt-lg">
            <q-btn unelevated color="primary" type="submit">{{
              ticketWaveDialog.editingWaveId
                ? $t('events.update_ticket_wave')
                : $t('events.save_ticket_wave')
            }}</q-btn>
            <q-btn
              flat
              color="grey"
              class="q-ml-auto"
              @click="resetTicketWaveDialog"
              v-text="$t('cancel')"
            ></q-btn>
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
