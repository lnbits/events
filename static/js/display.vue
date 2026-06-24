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
          <h5 class="q-mt-none" v-text="$t('events.buy_ticket')"></h5>
          <q-form @submit="createInvoice()" class="q-gutter-md">
            <div class="row">
              <div class="col-12">
                <q-input
                  filled
                  dense
                  v-model.trim="formDialog.data.name"
                  :label="$t('events.your_name_label')"
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
                      ? $t('events.your_email_delivery_label')
                      : $t('events.your_email_label')
                  "
                  :rules="[
                    val => !!val || $t('events.required'),
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
                  :label="$t('events.nostr_nip05_label')"
                  :hint="$t('events.nostr_nip05_hint')"
                ></q-input>
              </div>
            </div>
            <q-input
              v-if="event.extra?.conditional"
              filled
              dense
              v-model.trim="formDialog.data.refund"
              :label="$t('events.refund_label')"
              :rules="[val => !!val || $t('events.required')]"
              lazy-rules
              :hint="
                $t('events.refund_hint', {
                  min_tickets: event.extra?.min_tickets
                })
              "
            ></q-input>
            <q-select
              v-if="showTicketWaveSelector"
              filled
              dense
              v-model="formDialog.data.ticket_wave_id"
              emit-value
              map-options
              :label="$t('events.ticket_wave_label')"
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
                  :label="$t('events.promo_code_optional')"
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
                v-text="$t('events.submit')"
              ></q-btn>
              <q-btn
                @click="resetForm"
                flat
                color="grey"
                class="q-ml-auto"
                v-text="$t('clear')"
              ></q-btn>
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
            v-text="$t('events.link_to_ticket')"
          ></q-btn>
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
          <div
            class="text-h6 q-mb-sm"
            v-text="$t('events.continue_to_checkout')"
          ></div>
          <div
            class="text-body2 text-grey-5 q-mb-lg"
            v-text="$t('events.fiat_checkout_opened')"
          ></div>
          <q-btn
            unelevated
            color="primary"
            type="a"
            :href="receive.paymentReq"
            target="_blank"
            rel="noopener"
            v-text="$t('events.go_to_checkout')"
          ></q-btn>
        </div>
        <div class="row q-mt-lg">
          <q-btn
            outline
            color="grey"
            @click="utils.copyText(receive.paymentReq)"
            v-text="$t('events.copy_payment_link')"
          ></q-btn>
          <q-btn
            v-close-popup
            flat
            color="grey"
            class="q-ml-auto"
            v-text="$t('close')"
          ></q-btn>
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
            v-text="$t('events.copy_invoice')"
          ></q-btn>
          <q-btn
            v-close-popup
            flat
            color="grey"
            class="q-ml-auto"
            v-text="$t('close')"
          ></q-btn>
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
