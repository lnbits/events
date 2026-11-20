<template id="page-events-register">
  <div class="register-page">
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
          <div class="manual-entry">
            <q-input
              v-model="manualId"
              dense
              outlined
              clearable
              :label="$t('events.checkin_manual_label')"
              @keyup.enter="lookupManual"
            ></q-input>
            <q-btn
              class="q-mt-sm full-width"
              outline
              color="primary"
              :disable="!manualId || !token"
              @click="lookupManual"
              v-text="$t('events.checkin_manual_go')"
            ></q-btn>
            <div v-if="matches.length" class="match-list">
              <div v-for="m in matches" :key="m.id" class="match" @click="pickMatch(m)">
                <div class="match-name">
                  <span v-text="m.name || $t('events.anon')"></span>
                  <q-badge v-if="m.registered" color="red" v-text="$t('events.checkin_already_short')"></q-badge>
                </div>
                <div class="match-meta text-grey-6" v-text="matchLine(m)"></div>
              </div>
            </div>
            <div v-if="searched && !matches.length" class="text-caption text-grey-6 q-mt-sm" v-text="$t('events.checkin_no_matches')"></div>
          </div>
          <div v-if="!token" class="text-negative" v-text="$t('events.checkin_bad_token')"></div>
        </q-card-section>
      </q-card>

      <!-- what this ticket gets at the door -->
      <q-card v-if="lastScan" class="checkin-card">
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

          <div v-if="!shownBands.length" class="bandless-note" v-text="$t('events.checkin_no_bands')"></div>
          <div v-if="lastScan.checkin_text" class="door-msg" v-text="lastScan.checkin_text"></div>
          <div v-if="lastScan.note" class="door-note" v-text="lastScan.note"></div>

          <div v-if="!lastScan.already_checked_in" class="q-mt-md">
            <q-btn
              unelevated
              color="positive"
              class="full-width"
              :disable="busy"
              @click="confirmCheckin"
              v-text="$t('events.checkin_confirm')"
            ></q-btn>
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
          <qrcode-stream
            @detect="decodeQR"
            @error="onCameraError"
            class="rounded-borders"
          ></qrcode-stream>
          <div v-if="cameraError" class="text-negative q-mt-md" v-text="cameraError"></div>
        </div>
        <div class="row q-mt-lg">
          <q-btn @click="closeCamera" flat color="grey" class="q-ml-auto" v-text="$t('cancel')"></q-btn>
        </div>
      </q-card>
    </q-dialog>

  </div>
  </div>
</template>

<style>
  .checkin-status {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 11px 16px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-align: center;
    text-transform: uppercase;
    color: #fff;
  }
  /* The head says one thing: go (green) or stop (red). */
  .checkin-status.ok { background: #16a34a; }
  .checkin-status.warn { background: #d97706; }
  .checkin-status.bad { background: #dc2626; }
  .checkin-card { overflow: hidden; }
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
  .bandless-note { margin-top: 8px; font-size: 12px; opacity: 0.6; }
  .manual-entry { margin-top: 6px; }
  .match-list { margin-top: 6px; border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 8px; overflow: hidden; }
  .match { padding: 9px 11px; cursor: pointer; border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
  .match:last-child { border-bottom: none; }
  .match:active { background: rgba(255, 255, 255, 0.06); }
  .match-name { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14px; }
  .match-meta { font-size: 11px; }
  .scan-row { display: flex; justify-content: space-between; gap: 10px; padding: 5px 0; font-size: 12px; }
  .scan-name { font-weight: 600; }

</style>
