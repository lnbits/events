<template id="page-events-ticket">
  <div class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-8 col-lg-7 q-gutter-y-md">
      <q-card>
        <q-card-section>
          <div class="row items-center q-col-gutter-md">
            <div class="col-auto">
              <q-avatar
                :color="paid ? 'positive' : 'primary'"
                text-color="white"
                size="64px"
                :icon="paid ? 'check_circle' : 'hourglass_empty'"
              ></q-avatar>
            </div>
            <div class="col">
              <h4 class="q-my-xs" v-text="eventName"></h4>
              <div class="text-caption text-grey-7">
                <q-badge :color="deactivated ? 'negative' : (paid ? 'positive' : 'warning')" class="q-mt-xs">
                  <span v-text="ticketStatus"></span>
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
              <div class="text-caption text-grey-7" v-text="$t('events.col_ticket_type')"></div>
              <div class="text-body1" v-text="ticketTypeName"></div>
              <div v-if="ticketTypeName || ticketName" class="q-mt-sm">
                <div class="text-caption text-grey-7" v-text="$t('events.name_label')"></div>
                <div class="text-body1" v-text="ticketName"></div>
              </div>
              <div v-if="ticketEmail" class="text-caption q-mt-sm text-grey-7" v-text="ticketEmail"></div>
              <div v-if="purchaseDate" class="text-caption q-mt-sm text-grey-7">
                <span v-text="$t('events.purchase_date') + ': ' + purchaseDate"></span>
              </div>
            </div>
            <div class="col-12 col-sm-6 text-left text-sm-right">
              <div class="text-caption text-grey-7" v-text="$t('events.col_registered')"></div>
              <div class="q-mt-xs">
                <q-badge :color="registered ? 'positive' : 'grey'" outline>
                  <span v-text="registered ? $t('events.yes') : $t('events.no')"></span>
                </q-badge>
              </div>
            </div>
          </div>
        </q-card-section>

        <q-separator></q-separator>

        <q-card-section class="text-center">
          <lnbits-qrcode
            :value="`ticket://${ticketId}`"
            :options="{width: 500}"
            :show-buttons="false"
            :nfc="false"
          ></lnbits-qrcode>
          <div class="row q-col-gutter-sm justify-center q-mt-md">
            <div class="col-12 col-sm-auto">
              <q-btn unelevated color="positive" class="full-width" @click="copyTicketUrl">
                <span v-text="$t('events.copy_url')"></span>
              </q-btn>
            </div>
            <div class="col-12 col-sm-auto">
              <q-btn unelevated color="positive" class="full-width" @click="printWindow">
                <span v-text="$t('events.print')"></span>
              </q-btn>
            </div>
          </div>
        </q-card-section>
      </q-card>
    </div>
  </div>

  <Teleport to="body">
    <div class="ticket-print-sheet" v-if="printMode">
      <h3 class="ticket-print-event" v-text="eventName"></h3>
      <h5 v-if="ticketTypeName" class="ticket-print-type" v-text="ticketTypeName"></h5>
      <img class="ticket-print-qr" :src="qrSrc" alt="Ticket QR" v-if="qrSrc" />
    </div>
  </Teleport>
</template>

<style>
@media print {
  @page {
    size: auto;
    margin: 0;
  }

  html {
    font-size: 12px !important;
  }

  * {
    color: black !important;
    background: white !important;
    box-shadow: none !important;
  }

  body > * {
    display: none !important;
  }

  .ticket-print-sheet {
    display: flex !important;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100vw;
    min-height: 100vh;
    margin: 0 !important;
    padding: 0 !important;
    background: white !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .ticket-print-event {
    text-align: center;
    margin-bottom: 8px;
  }

  .ticket-print-type {
    text-align: center;
    margin-top: 0;
    margin-bottom: 20px;
    color: #666 !important;
  }

  .ticket-print-qr {
    display: block;
    width: 320px;
    height: 320px;
    object-fit: contain;
  }
}
</style>
