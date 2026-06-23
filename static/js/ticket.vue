<template id="page-events-ticket">
  <div class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card class="q-pa-lg">
        <q-card-section class="q-pa-none">
          <center>
            <h3
              class="q-my-none"
              v-text="$t('events.ticket_heading')"
            ></h3>
            <h5 v-if="ticket" v-text="ticket.name" class="q-my-none"></h5>
            <br />
            <h5
              class="q-my-none"
              v-text="$t('events.ticket_instructions')"
            ></h5>
            <div v-if="ticket" class="row justify-center q-gutter-sm q-mb-md">
              <q-btn
                unelevated
                :color="ticket.paid ? 'positive' : 'negative'"
                :label="
                  ticket.paid
                    ? $t('events.ticket_paid')
                    : $t('events.ticket_not_paid')
                "
              ></q-btn>
              <q-btn
                unelevated
                :color="ticket.registered ? 'positive' : 'warning'"
                :label="
                  ticket.registered
                    ? $t('events.checked_in')
                    : $t('events.not_checked_in')
                "
              ></q-btn>
            </div>
            <lnbits-qrcode
              :value="`ticket://${ticketId}`"
              :options="{width: 500}"
            ></lnbits-qrcode>
            <br />
            <q-btn @click="printWindow" color="grey">
              <q-icon left size="3em" name="print"></q-icon>
              <span v-text="$t('events.print')"></span>
            </q-btn>
          </center>
        </q-card-section>
      </q-card>
    </div>
  </div>

  <Teleport to="body">
    <div class="ticket-print-sheet" v-if="printMode">
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

  .ticket-print-qr {
    display: block;
    width: 320px;
    height: 320px;
    object-fit: contain;
  }
}
</style>
