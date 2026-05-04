<template id="page-events-register">
  <div class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card class="q-pa-lg">
        <q-card-section class="q-pa-none">
          <center>
            <h3 class="q-my-none">Registration</h3>
            <br />

            <br />

            <q-btn unelevated color="primary" @click="showCamera" size="xl"
              >Scan ticket</q-btn
            >
          </center>
        </q-card-section>
      </q-card>

      <q-card>
        <q-card-section>
          <q-table
            dense
            flat
            :rows="tickets"
            row-key="id"
            :columns="ticketsTable.columns"
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
                  <span v-text="col.value"></span>
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
          <q-btn @click="closeCamera" flat color="grey" class="q-ml-auto"
            >Cancel</q-btn
          >
        </div>
      </q-card>
    </q-dialog>
  </div>
</template>
