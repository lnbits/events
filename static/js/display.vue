<template id="page-events-display">
  <div v-if="event" class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card>
        <q-img
          v-if="event.banner"
          :src="event.banner"
          transition="slide-up"
          style="max-height: 300px"
          :img-style="{ objectFit: 'contain' }"
        ></q-img>
        <q-card-section class="q-pa-none">
          <h3 class="q-my-none q-pa-lg" v-text="event.name"></h3>
          <div class="q-px-lg q-pb-md" v-if="acceptedPaymentMethods.length > 0">
            <span class="text-caption">
              <span v-for="(method, idx) in acceptedPaymentMethods" :key="method">
                <q-icon
                  :name="method === 'ln' ? 'bolt' : method === 'onchain' ? 'link' : 'credit_card'"
                  size="xs"
                  class="q-mr-xs"
                ></q-icon>
                <span v-text="method === 'ln' ? 'LN' : method === 'onchain' ? 'BTC' : method.charAt(0).toUpperCase() + method.slice(1)"></span>
                <span v-if="idx < acceptedPaymentMethods.length - 1" class="q-mx-xs">|</span>
              </span>
            </span>
          </div>
          <div v-html="formatDescription" class="q-pa-lg"></div>
        </q-card-section>
      </q-card>

      <div
        v-if="ticketTypesLoaded && ticketTypes.length === 0 && !eventErrorLabel"
        class="q-pa-lg"
      >
        <q-banner class="bg-grey-3 text-grey-8">
          <template v-slot:avatar>
            <q-icon name="info" color="grey-8" />
          </template>
          <span v-text="$t('events.no_ticket_types_available')"></span>
        </q-banner>
      </div>

      <div v-for="tt in ticketTypes" :key="tt.id" class="q-mb-md">
        <q-card>
          <q-card-section>
            <div class="row items-center q-mb-sm">
              <h5 class="q-my-none" v-text="tt.name"></h5>
            </div>
            <div v-if="tt.description" class="text-body2 q-mb-sm" v-text="tt.description"></div>
            <div class="row q-col-gutter-sm q-mb-sm">
              <div class="col-auto">
                <q-chip color="primary" text-color="white">
                  {{ tt.price }} {{ basketCurrency }}
                </q-chip>
              </div>
              <div v-if="tt.max_tickets > 0 && tt.extra?.show_remaining && (tt.max_tickets - tt.sold <= (tt.extra.remaining_threshold || tt.max_tickets))" class="col-auto">
                <q-chip outline>
                  <template v-if="tt.max_tickets - tt.sold > 0">
                    {{ tt.max_tickets - tt.sold }} remaining
                  </template>
                  <template v-else>Sold out</template>
                </q-chip>
              </div>
              <div class="col-auto">
                <q-chip outline>
                  {{ $t('events.available_until') }} {{ tt.available_to }}
                </q-chip>
              </div>
            </div>
            <div class="row items-center q-col-gutter-sm">
              <div class="col-12 col-md-4">
                <q-input
                  filled
                  dense
                  v-model.number="itemQuantities[tt.id]"
                  type="number"
                  :label="$t('events.quantity')"
                  min="0"
                  :max="tt.max_tickets > 0 ? tt.max_tickets - tt.sold : undefined"
                ></q-input>
              </div>
              <div class="col-auto">
                <q-btn
                  unelevated
                  color="primary"
                  :label="$t('events.add_to_basket')"
                  :disable="!itemQuantities[tt.id] || itemQuantities[tt.id] <= 0"
                  @click="addToBasketBtn(tt)"
                ></q-btn>
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <q-input
        v-if="event.extra?.conditional"
        filled
        dense
        class="q-mb-md"
        v-model.trim="refundAddress"
        :label="$t('events.refund_label')"
        :hint="$t('events.refund_hint', {min_tickets: event.extra?.min_tickets})"
      ></q-input>

      <q-card
        v-if="basket.length > 0 || basketTotal > 0"
        ref="basketCard"
      >
        <q-card-section>
          <h5 class="q-mt-none" v-text="$t('events.basket')"></h5>
          <div v-for="bi in basket" :key="bi.ticketTypeId" class="row items-center q-mb-sm q-col-gutter-sm">
            <div class="col" v-text="`${bi.name} x${bi.quantity}`"></div>
            <div class="col-auto" v-text="`${bi.subtotal} ${basketCurrency}`"></div>
            <div class="col-auto">
              <q-btn
                flat
                dense
                round
                icon="delete"
                color="negative"
                @click="removeFromBasket(bi.ticketTypeId)"
              ></q-btn>
            </div>
          </div>

          <div v-if="basket.length > 0" class="q-mt-md q-gutter-md">
            <q-input
              filled
              dense
              v-model.trim="basketName"
              :label="$t('events.your_name_label')"
            ></q-input>
            <q-input
              filled
              dense
              v-model.trim="basketEmail"
              type="email"
              :label="$t('events.your_email_delivery_label')"
            ></q-input>
          </div>

          <div v-if="allowNostrNotifications" class="q-mt-md">
            <q-input
              filled
              dense
              v-model.trim="nostrIdentifier"
              :label="$t('events.nostr_nip05_label')"
              :hint="$t('events.nostr_nip05_hint')"
            ></q-input>
          </div>

          <div class="q-mt-md">
            <div class="row items-center q-col-gutter-sm">
              <div class="col">
                <q-input
                  filled
                  dense
                  v-model.trim="promoCodeInput"
                  :label="$t('events.promo_code_comma_separated')"
                  @keyup.enter="applyPromoCode"
                ></q-input>
              </div>
              <div class="col-auto">
                <q-btn
                  unelevated
                  color="primary"
                  :label="$t('events.apply')"
                  :loading="applyingPromo"
                  :disable="!basketItems.length"
                  @click="applyPromoCode"
                ></q-btn>
              </div>
            </div>
          </div>
          <div v-if="discountBreakdown.length > 0" class="q-mt-md">
            <div v-for="(d, idx) in discountBreakdown" :key="idx" class="text-caption text-positive">
              {{ d.label }}
            </div>
          </div>
          <div v-if="promoMessages.length > 0" class="q-mt-md">
            <div
              v-for="(m, idx) in promoMessages"
              :key="idx"
              class="text-caption"
              :class="m.kind === 'pending' ? 'text-warning' : 'text-negative'"
            >
              {{ m.label }}
            </div>
          </div>
          <div class="text-h6 q-mt-md text-right">
            Total: {{ basketTotal }} {{ basketCurrency }}
          </div>
          <div class="text-center q-mt-lg">
            <q-btn
              unelevated
              color="primary"
              :disable="!canCheckout"
              :loading="checkoutLoading"
              @click="checkout"
              v-text="$t('events.checkout')"
            ></q-btn>
          </div>
        </q-card-section>
      </q-card>

      <q-card
        v-if="basket.length > 0"
        class="q-mt-md"
        style="position: sticky; bottom: 16px; z-index: 10"
      >
        <q-card-section class="q-py-sm">
          <div class="row items-center no-wrap q-col-gutter-sm">
            <div class="col">
              <q-icon name="shopping_basket" size="sm" class="q-mr-xs"></q-icon>
              <span class="text-subtitle2" v-text="basketSummary"></span>
            </div>
            <div class="col-auto">
              <q-btn
                unelevated
                dense
                color="primary"
                icon="arrow_downward"
                :label="$t('events.view_basket')"
                @click="scrollToBasket"
              ></q-btn>
            </div>
          </div>
        </q-card-section>
      </q-card>

      <q-card v-show="ticketLink.show" class="q-pa-lg">
        <div class="text-center q-mb-lg">
          <q-btn
            unelevated
            size="xl"
            :href="ticketLink.data.link"
            target="_blank"
            color="primary"
            type="a"
            v-text="$t('events.link_to_ticket')"
          ></q-btn>
        </div>
      </q-card>
    </div>
  </div>
  <div
    v-else-if="eventErrorLabel"
    class="row q-col-gutter-md justify-center"
  >
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card class="q-pa-lg">
        <q-card-section class="q-pa-none">
          <h3 class="q-my-none q-pa-lg" v-text="eventErrorLabel"></h3>
        </q-card-section>
      </q-card>
    </div>
  </div>

  <div v-else class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <div class="text-center q-pa-lg">
        <q-spinner-bars color="primary" size="2em"></q-spinner-bars>
      </div>
    </div>
  </div>

  <q-dialog v-model="anonDialog">
    <q-card style="max-width: 460px">
      <q-card-section class="row items-center no-wrap">
        <q-icon name="lock" size="2em" color="primary" class="q-mr-md"></q-icon>
        <div class="text-h6" v-text="$t('events.anon_dialog_title')"></div>
        <q-space></q-space>
        <q-btn
          flat
          round
          dense
          icon="close"
          :aria-label="$q.lang.label.close"
          v-close-popup
        ></q-btn>
      </q-card-section>
      <q-card-section class="q-pt-none" v-text="$t('events.anon_dialog_body')"></q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          color="primary"
          :label="$t('events.anon_dialog_back')"
          v-close-popup
        ></q-btn>
        <q-btn
          unelevated
          color="primary"
          :label="$t('events.anon_dialog_confirm')"
          @click="confirmAnonCheckout"
        ></q-btn>
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
