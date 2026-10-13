<template id="page-events-basket">
  <div class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-8 col-lg-7 q-gutter-y-md">
      <q-card v-if="loading" class="q-pa-lg text-center">
        <q-spinner size="3em" />
        <p class="q-mt-md" v-text="$t('events.loading')"></p>
      </q-card>

      <q-card v-else-if="error" class="q-pa-lg">
        <q-card-section class="text-center">
          <q-icon name="warning" size="3em" color="negative" />
          <p class="q-mt-md" v-text="error"></p>
        </q-card-section>
      </q-card>

      <q-card v-else-if="!basket" class="q-pa-lg text-center">
        <q-icon name="shopping_basket" size="3em" color="grey" />
        <p class="q-mt-md" v-text="$t('events.basket_not_found')"></p>
      </q-card>

      <template v-else>
        <q-card>
          <div v-if="eventImageUrl" :style="bannerStyle" class="banner-header"></div>
          <q-card-section>
            <div class="row items-center q-col-gutter-md">
              <div class="col-auto">
                <q-avatar
                  :color="basket.paid ? 'positive' : 'primary'"
                  text-color="white"
                  size="64px"
                  :icon="basket.paid ? 'check_circle' : 'hourglass_empty'"
                ></q-avatar>
              </div>
              <div class="col">
                <h4 class="q-my-xs" v-text="eventName"></h4>
                <div class="text-caption text-grey-7">
                  <q-badge :color="basket.paid ? 'positive' : 'warning'" class="q-mt-xs">
                    <span v-text="basketStatus"></span>
                  </q-badge>
                </div>
              </div>
            </div>
          </q-card-section>
        </q-card>

        <q-card>
          <q-card-section>
            <div class="row q-col-gutter-md items-start">
              <div class="col-12 col-sm-6">
                <div class="text-caption text-grey-7" v-text="$t('events.buyer')"></div>
                <div class="text-body1" v-text="buyerName"></div>
                <div v-if="basket.email" class="text-caption text-grey-7" v-text="basket.email"></div>
                <div class="text-caption q-mt-xs text-grey-7">
                  Order ID:
                  <a v-if="basket.satspay_charge_id" :href="'/satspay/' + basket.satspay_charge_id" target="_blank" class="text-secondary">
                    <span v-text="basket.id"></span>
                  </a>
                  <span v-else v-text="basket.id"></span>
                </div>
                <div v-if="basket.time" class="text-caption q-mt-xs text-grey-7">
                  <span v-text="$t('events.purchase_date') + ': ' + formatDate(basket.time)"></span>
                </div>
              </div>
              <div class="col-12 col-sm-6 text-left text-sm-right">
                <div class="text-caption text-grey-7" v-text="$t('events.total')"></div>
                <div class="text-h5" v-text="formattedTotal"></div>
              </div>
            </div>
          </q-card-section>

          <q-separator></q-separator>

          <q-card-section>
            <div class="row items-center q-col-gutter-sm">
              <div class="col">
                <div
                  class="text-body1"
                  v-text="basket.paid ? $t('events.basket_confirmed') : $t('events.basket_pending')"
                ></div>
                <div
                  v-if="!basket.paid"
                  class="text-caption text-grey-7"
                  v-text="$t('events.basket_auto_update')"
                ></div>
              </div>
              <div v-if="!basket.paid" class="col-auto">
                <q-spinner color="primary" size="2em"></q-spinner>
              </div>
            </div>
          </q-card-section>
        </q-card>

        <q-card>
          <q-card-section>
            <div class="row items-center q-mb-sm">
              <div class="col">
                <div class="text-h6" v-text="$t('events.your_tickets')"></div>
                <div class="text-caption text-grey-7" v-text="ticketSummary"></div>
              </div>
            </div>

            <q-list separator>
              <q-item v-for="ticket in tickets" :key="ticket.id">
                <q-item-section avatar>
                  <q-avatar
                    :color="ticket.paid ? 'positive' : 'grey-5'"
                    text-color="white"
                    :icon="ticket.paid ? 'confirmation_number' : 'lock'"
                  ></q-avatar>
                </q-item-section>
                <q-item-section>
                  <q-item-label v-text="ticketName(ticket)"></q-item-label>
                  <q-item-label caption>
                    Ticket ID: <span v-text="ticket.id"></span>
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <q-btn
                    v-if="ticket.paid"
                    unelevated
                    dense
                    color="positive"
                    :to="`/events/ticket/${ticket.id}`"
                    :label="$t('events.show_ticket')"
                  ></q-btn>
                  <q-badge
                    v-else
                    color="grey-6"
                    v-text="$t('events.ticket_not_paid')"
                  ></q-badge>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>
        </q-card>

        <q-card>
          <q-card-section>
            <div class="row q-col-gutter-sm justify-center">
              <div v-if="!basket.paid && paymentLink" class="col-12 col-sm-auto">
                <q-btn
                  unelevated
                  color="positive"
                  class="full-width"
                  :href="paymentLink"
                  :label="$t('events.continue_payment')"
                ></q-btn>
              </div>
              <div class="col-12 col-sm-auto">
                <q-btn
                  unelevated
                  color="positive"
                  class="full-width"
                  :to="`/events/${basket.event_id}`"
                  :label="$t('events.buy_more')"
                ></q-btn>
              </div>
            </div>
          </q-card-section>
        </q-card>

      </template>
    </div>
  </div>
</template>
