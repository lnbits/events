<template id="page-events-display">
  <div v-if="event" class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card>
        <q-img
          v-if="event.banner"
          :src="event.banner"
          transition="slide-up"
        ></q-img>
        <q-card-section class="q-pa-none">
          <h3 class="q-my-none q-pa-lg" v-text="event.name"></h3>
          <div v-html="event.info" class="q-pa-lg"></div>
        </q-card-section>
      </q-card>
      <q-card class="q-pa-lg">
        <q-card-section class="q-pa-none">
          <h5 class="q-mt-none">Buy Ticket</h5>
          <q-form @submit="createInvoice()" class="q-gutter-md">
            <div class="row">
              <div class="col-12">
                <q-input
                  filled
                  dense
                  v-model.trim="formDialog.data.name"
                  label="Your name "
                  :rules="[val => nameValidation(val)]"
                ></q-input>
              </div>
              <div class="col-12 col-md-6 q-pr-sm">
                <q-input
                  filled
                  dense
                  v-model.trim="formDialog.data.email"
                  type="email"
                  :label="
                    allowEmailNotifications
                      ? 'Your email (ticket delivery) '
                      : 'Your email '
                  "
                  :rules="[
                    val => !!val || '* Required',
                    val => emailValidation(val)
                  ]"
                  lazy-rules
                ></q-input>
              </div>
              <div v-if="allowNostrNotifications" class="col-12 col-md-6">
                <q-input
                  filled
                  dense
                  v-model.trim="formDialog.data.nostr_identifier"
                  label="(optional) Nostr NIP-05"
                  hint="If provided, we'll DM your ticket link after payment."
                ></q-input>
              </div>
            </div>
            <q-input
              v-if="event.extra?.conditional"
              filled
              dense
              v-model.trim="formDialog.data.refund"
              label="Refund lnadress or LNURL "
              :rules="[val => !!val || '* Required']"
              lazy-rules
              :hint="`If minimum tickets (${event.extra?.min_tickets}) are not met, refund will be sent.`"
            ></q-input>
            <q-select
              v-if="showTicketWaveSelector"
              filled
              dense
              v-model="formDialog.data.ticket_wave_id"
              emit-value
              map-options
              label="Ticket wave"
              :options="
                activeTicketWaves.map(wave => ({
                  label: `${wave.title} - ${wave.price_per_ticket} ${wave.currency}`,
                  value: wave.id
                }))
              "
            ></q-select>
            <div class="row q-col-gutter-md q-pt-lg items-center">
              <div v-if="showPaymentMethodSelector" class="col-auto">
                <q-option-group
                  v-model="formDialog.data.payment_method"
                  inline
                  :options="paymentMethodOptions"
                ></q-option-group>
              </div>
              <div
                :class="
                  showPaymentMethodSelector ? 'col-12 col-md-3' : 'col-12'
                "
              >
                <q-input
                  filled
                  dense
                  v-model.trim="formDialog.data.promo_code"
                  label="(optional) Promo Code "
                ></q-input>
              </div>
            </div>
            <div class="row q-mt-lg">
              <q-btn
                unelevated
                color="primary"
                :disable="
                  formDialog.data.name == '' ||
                  formDialog.data.email == '' ||
                  (showTicketWaveSelector && !formDialog.data.ticket_wave_id) ||
                  (receive.show && Boolean(paymentReq))
                "
                type="submit"
                >Submit</q-btn
              >
              <q-btn @click="resetForm" flat color="grey" class="q-ml-auto"
                >Clear</q-btn
              >
            </div>
          </q-form>
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
            >Link to your ticket!</q-btn
          >
        </div>
      </q-card>
    </div>

    <q-dialog v-model="receive.show" position="top" @hide="closeReceiveDialog">
      <q-card
        v-if="!receive.paymentReq"
        class="q-pa-lg q-pt-xl lnbits__dialog-card"
      >
      </q-card>
      <q-card
        v-else-if="receive.isFiat"
        class="q-pa-lg q-pt-xl lnbits__dialog-card"
      >
        <div class="text-center q-mb-lg">
          <div class="text-h6 q-mb-sm">Continue to checkout</div>
          <div class="text-body2 text-grey-5 q-mb-lg">
            Your fiat checkout opened in a new tab. If it did not, use the
            button below.
          </div>
          <q-btn
            unelevated
            color="primary"
            type="a"
            :href="receive.paymentReq"
            target="_blank"
            rel="noopener"
          >
            Go to checkout
          </q-btn>
        </div>
        <div class="row q-mt-lg">
          <q-btn
            outline
            color="grey"
            @click="utils.copyText(receive.paymentReq)"
            >Copy payment link</q-btn
          >
          <q-btn v-close-popup flat color="grey" class="q-ml-auto">Close</q-btn>
        </div>
      </q-card>
      <q-card v-else class="q-pa-lg q-pt-xl lnbits__dialog-card">
        <div class="text-center q-mb-lg">
          <lnbits-qrcode
            :href="'lightning:' + receive.paymentReq"
            :value="'LIGHTNING:' + receive.paymentReq.toUpperCase()"
          ></lnbits-qrcode>
        </div>
        <div class="row q-mt-lg">
          <q-btn
            outline
            color="grey"
            @click="utils.copyText(receive.paymentReq)"
            >Copy invoice</q-btn
          >
          <q-btn v-close-popup flat color="grey" class="q-ml-auto">Close</q-btn>
        </div>
      </q-card>
    </q-dialog>
  </div>
  <div v-else class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card class="q-pa-lg">
        <q-card-section class="q-pa-none">
          <h3 class="q-my-none q-pa-lg" v-text="eventErrorLabel"></h3>
        </q-card-section>
      </q-card>
    </div>
  </div>
</template>
