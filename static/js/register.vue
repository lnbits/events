<template id="page-events-register">
  <div class="row q-col-gutter-md justify-center">
    <div class="col-12 col-md-7 col-lg-6 q-gutter-y-md">
      <q-card class="q-pa-lg">
        <q-card-section class="q-pa-none text-center">
          <h5 v-if="eventName" v-text="eventName" class="q-my-sm"></h5>
          <h3 class="q-my-xs" v-text="$t('events.registration')"></h3>
          <q-btn
            unelevated
            color="primary"
            @click="showCamera"
            size="xl"
            class="q-my-lg"
            :disable="!token"
          >
            <q-icon left name="qr_code_scanner" size="lg"></q-icon>
            <span v-text="$t('events.scan_ticket')"></span>
          </q-btn>
          <div v-if="!token" class="text-negative" v-text="$t('events.checkin_bad_token')"></div>
        </q-card-section>
      </q-card>

      <!-- what this ticket gets at the door -->
      <q-card v-if="lastScan">
        <div class="checkin-status" :class="statusClass">
          <q-icon :name="statusIcon" size="18px"></q-icon>
          <span v-text="statusText"></span>
        </div>

        <q-card-section v-if="lastScan.ticket">
          <div class="text-h5 text-weight-bold" v-text="lastScan.ticket.name || $t('events.anon')"></div>
          <div class="text-caption text-grey-6" v-text="lastScan.ticket_type_name || '-'"></div>

          <div class="band-list q-mt-md">
            <div
              v-for="band in shownBands"
              :key="band.id"
              class="band"
              :class="isLight(band.colour) ? 'band-light' : 'band-dark'"
              :style="{background: band.colour}"
            >
              <span class="band-name" v-text="band.name.toUpperCase()"></span>
              <span class="band-label" v-text="band.label"></span>
              <span class="band-qty">&times;1</span>
            </div>
          </div>

          <div v-if="!shownBands.length" class="door-note" v-text="$t('events.checkin_no_bands')"></div>
          <div v-if="lastScan.checkin_text" class="door-msg" v-text="lastScan.checkin_text"></div>
          <div v-if="lastScan.note" class="door-note" v-text="lastScan.note"></div>

          <div class="row q-col-gutter-sm q-mt-md">
            <div v-if="!lastScan.already_checked_in" class="col-12 col-sm-6">
              <q-btn
                unelevated
                color="positive"
                class="full-width"
                :loading="busy"
                @click="confirmCheckin"
                v-text="$t('events.checkin_confirm')"
              ></q-btn>
            </div>
            <div class="col-12 col-sm-6">
              <q-btn
                outline
                color="grey"
                class="full-width"
                @click="openOverride"
                v-text="$t('events.checkin_bands')"
              ></q-btn>
            </div>
          </div>
          <div
            v-if="lastScan.already_checked_in && lastScan.checked_in_at"
            class="text-caption text-grey-6 q-mt-sm"
            v-text="$t('events.checkin_at') + ': ' + shortTime(lastScan.checked_in_at)"
          ></div>
        </q-card-section>
      </q-card>

      <q-card v-if="recent.length">
        <q-card-section>
          <div class="text-caption text-grey-6 q-mb-sm" v-text="$t('events.checkin_scanned')"></div>
          <div v-for="t in recent" :key="t.id" class="scan-row">
            <span class="scan-name" v-text="t.name || $t('events.anon')"></span>
            <span class="text-grey-6" v-text="recentLine(t)"></span>
          </div>
        </q-card-section>
      </q-card>
    </div>

    <q-dialog v-model="sendCamera.show" position="top">
      <q-card class="q-pa-lg q-pt-xl">
        <div class="text-center q-mb-lg">
          <qrcode-stream @detect="decodeQR" class="rounded-borders"></qrcode-stream>
        </div>
        <div class="row q-mt-lg">
          <q-btn @click="closeCamera" flat color="grey" class="q-ml-auto" v-text="$t('cancel')"></q-btn>
        </div>
      </q-card>
    </q-dialog>

    <q-dialog v-model="overrideOpen">
      <q-card style="width: 360px; max-width: 92vw">
        <q-card-section>
          <div class="text-subtitle1 text-weight-medium" v-text="$t('events.checkin_override')"></div>
        </q-card-section>
        <q-card-section class="q-pt-none">
          <div
            v-for="band in allBands"
            :key="band.id"
            class="band-opt"
            :aria-pressed="String(overrideBands.includes(band.id))"
            @click="toggleBand(band.id)"
          >
            <span class="band-sw" :style="{background: band.colour}"></span>
            <span>
              <span class="band-opt-name" v-text="band.name"></span>
              <span class="band-opt-label" v-text="band.label"></span>
            </span>
            <q-icon
              v-if="overrideBands.includes(band.id)"
              name="check"
              color="positive"
              class="q-ml-auto"
            ></q-icon>
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat color="grey" v-text="$t('cancel')" @click="overrideOpen = false"></q-btn>
          <q-btn unelevated color="primary" :loading="busy" @click="saveOverride" v-text="$t('events.checkin_save')"></q-btn>
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<style>
  .checkin-status {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
  }
  .checkin-status.ok { background: rgba(22, 163, 74, 0.18); color: #4ade80; }
  .checkin-status.warn { background: rgba(245, 158, 11, 0.18); color: #fbbf24; }
  .checkin-status.bad { background: rgba(220, 38, 38, 0.18); color: #f87171; }
  .band-list { display: flex; flex-direction: column; gap: 8px; }
  .band {
    display: flex;
    align-items: center;
    gap: 10px;
    border-radius: 10px;
    padding: 11px 13px;
    border: 1px solid rgba(255, 255, 255, 0.16);
  }
  .band.band-light { color: #101010; }
  .band.band-dark { color: #ffffff; }
  .band-name { font-size: 18px; font-weight: 800; letter-spacing: 0.3px; }
  .band-label { font-size: 12px; opacity: 0.85; }
  .band-qty { margin-left: auto; font-size: 12px; font-weight: 800; opacity: 0.9; }
  .door-msg {
    margin-top: 10px;
    padding: 10px 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    font-size: 14px;
    line-height: 1.45;
  }
  .door-label {
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.6px;
    opacity: 0.6;
    margin-right: 6px;
  }
  .door-note { margin-top: 8px; font-size: 12px; color: #fbbf24; }
  .scan-row { display: flex; justify-content: space-between; gap: 10px; padding: 5px 0; font-size: 12px; }
  .scan-name { font-weight: 600; }
  .band-opt {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 10px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 10px;
    margin-bottom: 6px;
    cursor: pointer;
  }
  .band-opt[aria-pressed="true"] { border-color: #fff; }
  .band-sw {
    width: 28px;
    height: 28px;
    border-radius: 7px;
    border: 1px solid rgba(0, 0, 0, 0.4);
    flex: 0 0 auto;
  }
  .band-opt-name { display: block; font-size: 14px; font-weight: 700; }
  .band-opt-label { display: block; font-size: 11px; opacity: 0.65; }
</style>
