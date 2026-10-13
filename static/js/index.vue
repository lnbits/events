# page-events
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

                    <div class="row items-center q-gutter-x-sm q-mb-md">
                      <div
                        class="text-subtitle1"
                        v-text="$t('events.ticket_types')"
                      ></div>
                      <q-btn
                        unelevated
                        dense
                        size="sm"
                        icon="add"
                        color="primary"
                        @click="openTicketTypeDialog(props.row.id)"
                      ></q-btn>
                    </div>
                    <div class="column q-mb-lg">
                      <div
                        v-if="!ticketTypesByEvent[props.row.id] || ticketTypesByEvent[props.row.id].length === 0"
                        class="text-caption"
                        v-text="$t('events.no_ticket_types')"
                      ></div>
                      <div class="row q-gutter-sm">
                        <div
                          v-for="tt in (ticketTypesByEvent[props.row.id] || [])"
                          :key="tt.id"
                          class="col-auto"
                        >
                        <q-chip
                          square
                          clickable
                          class="q-py-xs"
                          :class="{ 'text-strikethrough': !(tt.extra?.active ?? true) }"
                          style="height: auto"
                          @click="openTicketTypeDialog(props.row.id, tt)"
                        >
                          <span
                            style="white-space: normal; line-height: 1.3"
                            v-text="ticketTypeChipLabel(tt)"
                          ></span>
                        </q-chip>
                      </div>
                      </div>
                    </div>

                    <div class="row items-center q-gutter-x-sm q-mb-md">
                      <div
                        class="text-subtitle1"
                        v-text="$t('events.promo_codes')"
                      ></div>
                      <q-btn
                        unelevated
                        dense
                        size="sm"
                        icon="add"
                        color="primary"
                        @click="openAddPromoCodeDialog(props.row.id)"
                      ></q-btn>
                    </div>
                    <div class="column q-gutter-y-sm">
                      <div
                        v-if="(props.row.extra.promo_codes || []).length == 0"
                        class="text-caption"
                        v-text="$t('events.no_promo_codes')"
                      ></div>
                      <div class="row q-gutter-sm">
                        <div
                          v-for="(
                            code, index
                          ) in (props.row.extra.promo_codes || [])"
                          :key="index"
                          class="col-auto"
                        >
                          <q-chip
                            square
                            clickable
                            class="q-py-xs"
                            style="height: auto"
                            :class="{ 'text-strikethrough': !code.active }"
                            @click="openEditPromoCodeDialog(props.row.id, index)"
                          >
                            <span
                              style="white-space: normal; line-height: 1.3"
                              v-text="promoChipLabel(code, props.row.currency)"
                            ></span>
                          </q-chip>
                        </div>
                      </div>
                    </div>

                    <q-separator class="q-my-md"></q-separator>
                    <div class="text-subtitle1 q-mb-sm" v-text="$t('events.bulk_actions')"></div>
                    <div class="row q-col-gutter-sm">
                      <div class="col-auto">
                        <q-btn
                          unelevated
                          dense
                          color="primary"
                          :label="$t('events.resend_all_emails')"
                          :loading="resendingAllEmailsFor.includes(props.row.id)"
                          @click="resendAllTicketEmails(props.row.id)"
                        ></q-btn>
                      </div>
                      <div class="col-auto">
                        <q-btn
                          outline
                          dense
                          color="primary"
                          :label="$t('events.email_all_attendees')"
                          @click="openEmailAllDialog(props.row.id)"
                        ></q-btn>
                      </div>
                      <div class="col-auto">
                        <q-btn
                          outline
                          dense
                          color="secondary"
                          :label="$t('events.preview_ticket_email')"
                          :href="previewTicketEmailUrl(props.row)"
                          target="_blank"
                        ></q-btn>
                      </div>
                      <div class="col-auto">
                        <q-btn
                          outline
                          dense
                          color="secondary"
                          :label="$t('events.preview_admin_email')"
                          :href="previewAdminEmailUrl(props.row)"
                          target="_blank"
                        ></q-btn>
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
                <q-th auto-width></q-th>
                <q-th auto-width></q-th>
                <q-th v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.label"></span>
                </q-th>
                <q-th auto-width>
                  {{ $t('events.col_satspay') }}
                </q-th>
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
                </q-td>

                <q-td auto-width>
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="toggleTicketDeactivation(props.row)"
                    :icon="props.row.extra?.deactivated ? 'check_circle' : 'block'"
                    :color="props.row.extra?.deactivated ? 'positive' : 'orange'"
                  >
                    <q-tooltip>
                      <span v-text="props.row.extra?.deactivated ? $t('events.activate_ticket') : $t('events.deactivate_ticket')"></span>
                    </q-tooltip>
                  </q-btn>
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

                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.value"></span>
                </q-td>

                <q-td auto-width>
                  <a
                    v-if="props.row.extra?.satspay_charge_id"
                    :href="'/satspay/' + props.row.extra.satspay_charge_id"
                    target="_blank"
                    class="text-secondary"
                  >
                    {{ shortenId(props.row.extra.satspay_charge_id) }}
                  </a>
                  <span v-else class="text-grey">—</span>
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
            <q-input
              class="col"
              filled
              dense
              v-model.trim="formDialog.data.name"
              type="name"
              :label="$t('events.event_title_label')"
            ></q-input>
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
          <q-input
            filled
            dense
            v-model.trim="formDialog.data.admin_email"
            type="email"
            :label="$t('events.admin_email_label')"
            :hint="$t('events.admin_email_hint')"
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
          <div class="row q-mt-md">
            <div class="col-4" v-text="$t('events.currency_unit')"></div>
            <div class="col-8">
              <q-select
                filled
                dense
                v-model="formDialog.data.currency"
                :options="currencies"
              ></q-select>
            </div>
          </div>
          <q-separator class="q-my-md"></q-separator>
          <div>
            <div class="text-subtitle1 q-mb-md">{{ $t('events.payment_methods') }}</div>
            <div class="row items-center q-mb-sm">
              <div class="col-3">
                <q-checkbox
                  v-model="paymentMethods.ln"
                  :label="$t('events.lightning')"
                  left-label
                ></q-checkbox>
              </div>
              <div class="col">
                <q-select
                  v-if="paymentMethods.ln"
                  filled
                  dense
                  emit-value
                  v-model="formDialog.data.extra.ln_wallet_id"
                  :options="g.user.walletOptions"
                  :label="$t('events.ln_wallet_label')"
                ></q-select>
              </div>
            </div>
            <div class="row items-center q-mb-sm">
              <div class="col-3">
                <q-checkbox
                  v-if="watchonlyWallets.length > 0"
                  v-model="paymentMethods.onchain"
                  :label="$t('events.onchain')"
                  left-label
                ></q-checkbox>
                <q-checkbox v-else :value="false" :label="$t('events.onchain')" left-label disabled>
                  <q-tooltip>{{ $t('events.onchain_disabled_hint') }}</q-tooltip>
                </q-checkbox>
              </div>
              <div class="col">
                <q-select
                  v-if="paymentMethods.onchain"
                  filled
                  dense
                  emit-value
                  v-model="formDialog.data.extra.onchain_wallet_id"
                  :options="watchonlyWallets"
                  :label="$t('events.onchain_wallet_label')"
                ></q-select>
              </div>
            </div>
            <div class="row items-center">
              <div class="col-3">
                <q-checkbox
                  v-model="paymentMethods.fiat"
                  :label="$t('events.fiat')"
                  left-label
                ></q-checkbox>
              </div>
              <div class="col">
                <q-select
                  v-if="paymentMethods.fiat && g.user.fiat_providers && g.user.fiat_providers.length"
                  filled
                  dense
                  emit-value
                  v-model="formDialog.data.extra.fiat_provider"
                  :options="g.user.fiat_providers"
                  :label="$t('events.fiat_provider_label')"
                ></q-select>
                <span
                  v-if="paymentMethods.fiat && (!g.user.fiat_providers || !g.user.fiat_providers.length)"
                  class="text-caption"
                  v-text="$t('events.fiat_provider_hint')"
                ></span>
              </div>
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
          <div class="q-mb-sm">
            <q-toggle
              v-model="formDialog.data.extra.email_notifications"
              :label="$t('events.email_notifications')"
              left-label
              :disable="!g.settings.emailConfigured"
            ></q-toggle>
            <div v-if="!g.settings.emailConfigured" class="text-negative text-caption q-ml-lg" v-text="$t('events.email_not_configured')"></div>
          </div>
          <div class="q-mb-sm">
            <q-toggle
              v-model="formDialog.data.extra.nostr_notifications"
              :label="$t('events.nostr_notifications')"
              left-label
              :disable="!g.settings.nostrConfigured"
            ></q-toggle>
            <div v-if="!g.settings.nostrConfigured" class="text-negative text-caption q-ml-lg" v-text="$t('events.nostr_not_configured')"></div>
          </div>
          <div
            v-if="formDialog.data.extra.email_notifications || formDialog.data.extra.nostr_notifications"
            class="q-mt-md"
          >
            <q-input
              v-if="formDialog.data.extra.email_notifications"
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
          <q-separator class="q-my-md"></q-separator>
          <div
            class="text-subtitle1 q-mb-md"
            v-text="$t('events.conditional_events_title')"
          ></div>
          <div
            class="text-caption"
            v-text="$t('events.conditional_events_desc')"
          ></div>
          <div class="row">
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
                formDialog.data.name == null ||
                formDialog.data.info == null ||
                formDialog.data.event_start_date == null ||
                formDialog.data.event_end_date == null ||
                (!paymentMethods.ln && !paymentMethods.onchain && !paymentMethods.fiat) ||
                (paymentMethods.ln && !formDialog.data.extra?.ln_wallet_id) ||
                (paymentMethods.onchain && !formDialog.data.extra?.onchain_wallet_id)
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

    <q-dialog v-model="ticketTypeDialog.show" position="top">
      <q-card class="q-pa-lg q-pt-xl lnbits__dialog-card">
        <q-form @submit="saveTicketType" class="q-gutter-md">
          <div
            class="text-subtitle1"
            v-text="
              ticketTypeDialog.isEdit
                ? $t('events.edit_ticket_type')
                : $t('events.add_ticket_type')
            "
          ></div>
          <q-input
            filled
            dense
            v-model.trim="ticketTypeDialog.data.name"
            type="text"
            :label="$t('events.tt_name_label')"
          ></q-input>
          <q-input
            filled
            dense
            v-model.trim="ticketTypeDialog.data.description"
            type="textarea"
            :label="$t('events.tt_description_label')"
          ></q-input>
          <q-input
            filled
            dense
            v-model.trim="ticketTypeDialog.data.image_url"
            type="url"
            :label="$t('events.tt_image_url_label')"
          >          </q-input>
          <q-input
            filled
            dense
            v-model.number="ticketTypeDialog.data.price"
            type="number"
            :label="$t('events.price_label', {currency: getEventCurrency(ticketTypeDialog.eventId)})"
            min="0"
          ></q-input>
          <div class="row">
            <div class="col q-mr-xs">
              <q-input
                filled
                dense
                v-model.number="ticketTypeDialog.data.max_tickets"
                type="number"
                :label="$t('events.amount_tickets_label')"
                min="0"
                :hint="$t('events.max_tickets_hint')"
              ></q-input>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.number="ticketTypeDialog.data.sort_order"
                type="number"
                :label="$t('events.sort_order_label')"
                min="0"
              ></q-input>
            </div>
          </div>
          <div class="row">
            <div class="col q-mr-xs">
              <q-input
                filled
                dense
                v-model.trim="ticketTypeDialog.data.available_from"
                type="date"
                :label="$t('events.available_from_label')"
              ></q-input>
            </div>
            <div class="col">
              <q-input
                filled
                dense
                v-model.trim="ticketTypeDialog.data.available_to"
                type="date"
                :label="$t('events.available_to_label')"
              ></q-input>
            </div>
          </div>
          <q-toggle
            v-model="ticketTypeDialog.data.active"
            :label="ticketTypeDialog.data.active ? $t('events.active') : $t('events.inactive')"
            left-label
          ></q-toggle>
          <q-toggle
            v-model="ticketTypeDialog.data.show_remaining"
            :label="$t('events.show_remaining_label')"
            left-label
          ></q-toggle>
          <q-input
            v-if="ticketTypeDialog.data.show_remaining"
            filled
            dense
            v-model.number="ticketTypeDialog.data.remaining_threshold"
            type="number"
            :label="$t('events.remaining_threshold_label')"
            :hint="$t('events.remaining_threshold_hint')"
            min="0"
          ></q-input>
          <q-input
            filled
            dense
            v-model.number="ticketTypeDialog.data.admits"
            type="number"
            :label="$t('events.admits_label')"
            :hint="$t('events.admits_hint')"
            min="1"
          ></q-input>
          <q-input
            filled
            dense
            v-model.trim="ticketTypeDialog.data.cap_group"
            type="text"
            :label="$t('events.cap_group_label')"
            :hint="$t('events.cap_group_hint')"
          ></q-input>
          <div class="row q-mt-lg">
            <q-btn
              v-if="ticketTypeDialog.isEdit"
              unelevated
              color="negative"
              icon="delete"
              @click="deleteTicketType(ticketTypeDialog.data)"
              v-text="$t('delete')"
            ></q-btn>
            <div class="row q-gutter-sm q-ml-auto">
              <q-btn
                flat
                color="grey"
                @click="resetTicketTypeDialog"
                v-text="$t('cancel')"
              ></q-btn>
              <q-btn
                unelevated
                color="primary"
                type="submit"
                v-text="$t('events.save')"
              ></q-btn>
            </div>
          </div>
        </q-form>
      </q-card>
    </q-dialog>

    <q-dialog v-model="editPromoCodeDialog.show" position="top">
      <q-card class="q-pa-lg q-pt-xl lnbits__dialog-card" style="max-width: 500px">
        <q-form @submit="saveEditPromoCode" class="q-gutter-md">
          <div
            class="text-subtitle1"
            v-text="editPromoCodeDialog.codeIndex === -1 ? $t('events.add_promo_code') : $t('events.edit_promo_code')"
          ></div>

          <div
            v-if="editPromoCodeDialog.data"
            class="text-caption"
            style="font-style: italic"
            v-text="promoSummary(editPromoCodeDialog.data, editPromoCodeDialog.eventId)"
          ></div>

          <q-separator class="q-my-md"></q-separator>
          <div
            class="text-caption text-uppercase text-weight-medium"
            v-text="$t('events.promo_sec_identity')"
          ></div>
          <q-input
            filled
            dense
            v-model.trim="editPromoCodeDialog.data.title"
            type="text"
            :label="$t('events.promo_title_label')"
            :hint="$t('events.promo_title_hint')"
          ></q-input>
          <q-input
            filled
            dense
            v-model.trim="editPromoCodeDialog.data.code"
            type="text"
            :label="$t('events.promo_code_label')"
            :hint="
              editPromoCodeDialog.data.source.require_ticket
                ? $t('events.promo_code_optional_hint')
                : $t('events.promo_code_required_hint')
            "
          ></q-input>
          <q-toggle
            v-model="editPromoCodeDialog.data.active"
            :label="
              editPromoCodeDialog.data.active
                ? $t('events.active')
                : $t('events.inactive')
            "
          ></q-toggle>

          <q-separator class="q-my-md"></q-separator>
          <div
            class="text-caption text-uppercase text-weight-medium"
            v-text="$t('events.promo_sec_effect')"
          ></div>
          <q-btn-toggle
            :model-value="editPromoCodeDialog.data.grants ? 'grants' : 'discount'"
            :options="[
              {label: $t('events.promo_effect_discount'), value: 'discount'},
              {label: $t('events.promo_effect_grants'), value: 'grants'}
            ]"
            @update:model-value="
              onPromoEffectChange(editPromoCodeDialog.data, $event === 'grants')
            "
            toggle-color="primary"
            spread
            no-caps
            size="sm"
          ></q-btn-toggle>

          <template v-if="!editPromoCodeDialog.data.grants">
            <q-btn-toggle
              v-model="editPromoCodeDialog.discountType"
              :options="[
                {label: $t('events.discount_percent_label'), value: 'percent'},
                {label: $t('events.discount_fixed_label'), value: 'fixed'}
              ]"
              toggle-color="primary"
              spread
              no-caps
              size="sm"
            ></q-btn-toggle>
            <q-input
              v-if="editPromoCodeDialog.discountType !== 'fixed'"
              filled
              dense
              v-model.number="editPromoCodeDialog.data.discount_percent"
              type="number"
              :label="$t('events.discount_percent_label')"
              min="0"
              max="100"
            >
              <template v-slot:after><span>%</span></template>
            </q-input>
            <q-input
              v-else
              filled
              dense
              v-model.number="editPromoCodeDialog.data.discount_fixed"
              type="number"
              :label="$t('events.discount_fixed_label')"
              min="0"
            >
              <template v-slot:after>
                <span>{{ getEventCurrency(editPromoCodeDialog.eventId) }}</span>
              </template>
            </q-input>
            <div class="text-caption" v-text="$t('events.promo_applies_to')"></div>
            <q-btn-toggle
              :model-value="editPromoCodeDialog.data.ticket_type_ids ? 'types' : 'whole'"
              :options="[
                {label: $t('events.promo_applies_whole'), value: 'whole'},
                {label: $t('events.promo_applies_types'), value: 'types'}
              ]"
              @update:model-value="
                onPromoAppliesToChange(editPromoCodeDialog.data, $event)
              "
              toggle-color="primary"
              spread
              no-caps
              size="sm"
            ></q-btn-toggle>
            <q-select
              v-if="editPromoCodeDialog.data.ticket_type_ids"
              filled
              dense
              multiple
              use-chips
              emit-value
              map-options
              v-model="editPromoCodeDialog.data.ticket_type_ids"
              :options="ticketTypeOptions(editPromoCodeDialog.eventId)"
              :label="$t('events.promo_ticket_type_scope')"
              :hint="$t('events.promo_ticket_type_scope_hint')"
            ></q-select>
          </template>

          <template v-else>
            <q-select
              filled
              dense
              emit-value
              map-options
              v-model="editPromoCodeDialog.data.grants.ticket_type_id"
              :options="ticketTypeOptions(editPromoCodeDialog.eventId)"
              :label="$t('events.promo_grants_ticket_type')"
            ></q-select>
            <q-input
              filled
              dense
              v-model.number="editPromoCodeDialog.data.grants.per_source"
              type="number"
              min="1"
              :label="$t('events.promo_grants_per_source')"
              :hint="$t('events.promo_grants_per_source_hint')"
            ></q-input>
            <div
              class="text-caption"
              v-text="
                $t('events.promo_grants_hint', {
                  per: editPromoCodeDialog.data.grants.per_source || 1
                })
              "
            ></div>
          </template>

          <q-separator class="q-my-md"></q-separator>
          <div
            class="text-caption text-uppercase text-weight-medium"
            v-text="$t('events.promo_sec_condition')"
          ></div>
          <q-toggle
            v-model="editPromoCodeDialog.data.source.require_ticket"
            :label="$t('events.promo_require_ticket')"
            @update:model-value="onPromoRequireTicketChange($event)"
          ></q-toggle>
          <div
            class="text-caption q-mt-none"
            v-text="$t('events.promo_require_ticket_hint')"
          ></div>

          <template v-if="editPromoCodeDialog.data.source.require_ticket">
            <q-select
              filled
              dense
              multiple
              use-chips
              emit-value
              map-options
              v-model="editPromoCodeDialog.data.source.event_ids"
              :options="sourceEventOptions(editPromoCodeDialog.eventId)"
              :label="$t('events.promo_source_events')"
              :hint="$t('events.promo_source_events_hint')"
            ></q-select>
            <q-select
              filled
              dense
              multiple
              use-chips
              emit-value
              map-options
              v-model="editPromoCodeDialog.data.source.ticket_type_ids"
              :options="
                sourceTicketTypeOptions(
                  editPromoCodeDialog.data.source,
                  editPromoCodeDialog.eventId
                )
              "
              :label="$t('events.promo_source_ticket_types')"
              :hint="$t('events.promo_source_ticket_types_hint')"
            ></q-select>

            <template v-if="!editPromoCodeDialog.data.grants">
              <q-select
                filled
                dense
                emit-value
                map-options
                v-model="editPromoCodeDialog.data.source.credit"
                :options="[
                  {label: $t('events.promo_source_credit_none'), value: 'none'},
                  {label: $t('events.promo_source_credit_paid'), value: 'paid'}
                ]"
                :label="$t('events.promo_source_credit')"
                :hint="$t('events.promo_source_credit_hint')"
              ></q-select>
              <q-toggle
                v-model="editPromoCodeDialog.data.source.move"
                :label="$t('events.promo_source_move')"
                @update:model-value="onPromoMoveChange($event)"
              ></q-toggle>
              <div
                class="text-caption q-mt-none"
                v-text="$t('events.promo_source_move_hint')"
              ></div>
            </template>

            <q-input
              v-if="!editPromoCodeDialog.data.source.move"
              filled
              dense
              v-model.number="editPromoCodeDialog.data.max_tickets"
              type="number"
              min="1"
              :label="$t('events.promo_max_tickets')"
              :hint="$t('events.promo_max_tickets_hint')"
            ></q-input>
          </template>

          <q-separator class="q-my-md"></q-separator>
          <div
            class="text-caption text-uppercase text-weight-medium"
            v-text="$t('events.promo_sec_limits')"
          ></div>
          <q-input
            filled
            dense
            v-model.number="editPromoCodeDialog.data.max_uses"
            type="number"
            min="1"
            :label="$t('events.promo_max_uses')"
            :hint="$t('events.promo_max_uses_hint')"
          ></q-input>
          <q-input
            v-if="editPromoCodeDialog.data.source.require_ticket"
            filled
            dense
            v-model.number="editPromoCodeDialog.data.redemptions_per_ticket"
            type="number"
            min="1"
            :label="$t('events.promo_redemptions_per_ticket')"
            :hint="$t('events.promo_redemptions_per_ticket_hint')"
          ></q-input>
          <q-toggle
            v-model="editPromoCodeDialog.data.combinable"
            :label="$t('events.promo_combinable')"
          ></q-toggle>

          <template v-if="editPromoCodeDialog.codeIndex !== -1">
            <q-separator class="q-my-md"></q-separator>
            <div
              class="text-caption text-uppercase text-weight-medium"
              v-text="$t('events.promo_sec_usage')"
            ></div>
            <div
              class="text-caption"
              v-if="
                editPromoCodeDialog.data.max_uses != null &&
                editPromoCodeDialog.data.max_uses > 0
              "
              v-text="
                $t('events.promo_uses_label', {
                  used: editPromoCodeDialog.data.used_count || 0,
                  max: editPromoCodeDialog.data.max_uses
                })
              "
            ></div>
            <div
              class="text-caption"
              v-else
              v-text="
                $t('events.promo_uses_unlimited', {
                  used: editPromoCodeDialog.data.used_count || 0
                })
              "
            ></div>
          </template>

          <div class="row q-mt-lg">
            <q-btn
              v-if="editPromoCodeDialog.codeIndex >= 0"
              unelevated
              color="negative"
              icon="delete"
              @click="deletePromoCode(editPromoCodeDialog.eventId, editPromoCodeDialog.codeIndex)"
              v-text="$t('delete')"
            ></q-btn>
            <div class="row q-gutter-sm q-ml-auto">
              <q-btn
                flat
                color="grey"
                @click="editPromoCodeDialog.show = false"
                v-text="$t('cancel')"
              ></q-btn>
              <q-btn
                unelevated
                color="primary"
                type="submit"
                v-text="$t('events.save')"
              ></q-btn>
            </div>
          </div>
        </q-form>
      </q-card>
    </q-dialog>

    <q-dialog v-model="emailAllDialog.show" position="top">
      <q-card class="q-pa-lg q-pt-xl lnbits__dialog-card">
        <q-form @submit="sendEmailToAttendees" class="q-gutter-md">
          <div
            class="text-subtitle1"
            v-text="$t('events.email_all_attendees_title')"
          ></div>
          <q-input
            filled
            dense
            v-model.trim="emailAllDialog.subject"
            type="text"
            :label="$t('events.email_subject_label')"
            :rules="[val => !!val || $t('events.required')]"
          ></q-input>
          <q-input
            filled
            dense
            v-model.trim="emailAllDialog.message"
            type="textarea"
            :label="$t('events.email_message_label')"
            :rules="[val => !!val || $t('events.required')]"
          ></q-input>
          <div class="row q-mt-lg">
            <q-btn
              unelevated
              color="primary"
              type="submit"
              :loading="emailAllDialog.loading"
              v-text="$t('events.send')"
            ></q-btn>
            <q-btn
              flat
              color="grey"
              class="q-ml-auto"
              @click="resetEmailAllDialog"
              v-text="$t('cancel')"
            ></q-btn>
          </div>
        </q-form>
      </q-card>
    </q-dialog>

  </div>
</template>
<style>
.text-strikethrough {
  text-decoration: line-through;
}
</style>
