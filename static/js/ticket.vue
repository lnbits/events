<template id="page-events-ticket">
  <div class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card class="q-pa-lg">
        <q-card-section class="q-pa-none">
          <center>
            <h3 class="q-my-none">Ticket</h3>
            <h5 v-if="ticket" v-text="ticket.name" class="q-my-none"></h5>
            <br />
            <h5 class="q-my-none">
              Bookmark, print or screenshot this page,<br />
              and present it for registration!
            </h5>
            <div v-if="ticket" class="row justify-center q-gutter-sm q-mb-md">
              <q-btn
                unelevated
                :color="ticket.paid ? 'positive' : 'negative'"
                :label="ticket.paid ? 'Paid' : 'Not Paid'"
              ></q-btn>
              <q-btn
                unelevated
                :color="ticket.registered ? 'positive' : 'warning'"
                :label="ticket.registered ? 'Checked In' : 'Not Checked In'"
              ></q-btn>
            </div>
            <lnbits-qrcode
              :value="`ticket://${ticketId}`"
              :options="{width: 500}"
            ></lnbits-qrcode>
            <br />
            <q-btn @click="printWindow" color="grey">
              <q-icon left size="3em" name="print"></q-icon> Print
            </q-btn>
          </center>
        </q-card-section>
      </q-card>
    </div>
  </div>
</template>
