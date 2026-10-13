<template id="page-events-register">
  <div class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card class="q-pa-lg">
        <q-card-section class="q-pa-none text-center">
          <h5 v-if="eventName" v-text="eventName" class="q-my-sm"></h5>
          <h3 class="q-my-xs" v-text="$t('events.registration')"></h3>
          <q-btn unelevated color="primary" @click="showCamera" size="xl" class="q-my-lg">
            <q-icon left name="qr_code_scanner" size="lg"></q-icon>
            <span v-text="$t('events.scan_ticket')"></span>
          </q-btn>
        </q-card-section>
      </q-card>

      <q-card v-if="lastScan" :class="lastScan.success ? 'bg-positive' : 'bg-negative'">
        <q-card-section class="text-white text-center">
          <div v-if="lastScan.success">
            <q-icon name="check_circle" size="3em" color="white" class="q-mb-sm"></q-icon>
            <div class="text-h6 q-mb-sm" v-text="lastScan.ticket.name || $t('events.anon')"></div>
            <div class="text-caption" v-text="$t('events.col_ticket_type') + ': ' + (lastScan.ticket.ticket_type_name || '-')"></div>
            <div class="text-caption">
              ID:
              <a :href="'/events/ticket/' + lastScan.ticket.id" target="_blank" class="text-white" v-text="lastScan.ticket.id"></a>
            </div>
          </div>
          <div v-else>
            <q-icon name="cancel" size="3em" color="white" class="q-mb-sm"></q-icon>
            <div class="text-h6 q-mb-sm" v-text="$t('events.failed')"></div>
            <div class="text-caption" v-text="lastScan.error"></div>
          </div>
        </q-card-section>
      </q-card>

      <q-card>
        <q-card-section>
          <q-table
            dense
            flat
            :rows="tickets"
            row-key="id"
            :columns="ticketsColumns"
            v-model:pagination="ticketsTable.pagination"
          >
            <template v-slot:header="props">
              <q-tr :props="props">
                <q-th v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.label"></span>
                </q-th>
              </q-tr>
            </template>
            <template v-slot:body="props">
              <q-tr :props="props">
                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                  <a v-if="col.name === 'id'" :href="'/events/ticket/' + col.value" target="_blank" class="text-white" v-text="col.value"></a>
                  <span v-else v-text="col.value"></span>
                </q-td>
              </q-tr>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </div>

    <q-dialog v-model="sendCamera.show" position="top">
      <q-card class="q-pa-lg q-pt-xl">
        <div class="text-center q-mb-lg">
          <qrcode-stream
            @detect="decodeQR"
            class="rounded-borders"
          ></qrcode-stream>
        </div>
        <div class="row q-mt-lg">
          <q-btn
            @click="closeCamera"
            flat
            color="grey"
            class="q-ml-auto"
            v-text="$t('cancel')"
          ></q-btn>
        </div>
      </q-card>
    </q-dialog>
  </div>
</template>
