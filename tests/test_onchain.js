const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')

function page(data) {
  const context = {
    window: {},
    _: {findWhere: (items, query) => items.find(w => w.id === query.id)},
    LNbits: {
      api: {request: async () => ({data})},
      utils: {
        notifyApiError: error => {
          throw error
        }
      }
    }
  }
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, '../static/js/index.js'), 'utf8'),
    context
  )
  const component = context.window.PageEvents
  const state = {
    g: {user: {wallets: [{id: 'merchant', adminkey: 'key'}]}},
    formDialog: {
      data: {wallet: 'merchant', extra: {onchain_wallet_id: 'watch-id'}}
    },
    onchainWallets: [],
    coreOnchainWallets: [],
    $t: key => key
  }
  return {component, state}
}

test('core choices precede watchonly and loading preserves saved selections', async () => {
  const {component, state} = page({
    available: true,
    wallets: [{id: 'watch-id', title: 'Cold'}],
    core_wallets: [
      {id: 'core-id', name: 'Savings', status: 'ready'},
      {id: 'setup-id', name: 'New', status: 'setup'}
    ]
  })
  await component.methods.loadOnchainWallets.call(state)
  const options = component.computed.onchainWalletOptions.call(state)
  assert.deepEqual(
    Array.from(options, option => option.value),
    ['core:core-id', 'core:setup-id', 'watch-id']
  )
  assert.equal(options[0].label, 'LNbits: Savings')
  assert.match(options[1].label, /not_ready/)
  assert.equal(options[2].label, 'Watchonly: Cold')
  assert.equal(state.formDialog.data.extra.onchain_wallet_id, 'watch-id')
  state.formDialog.data.extra.onchain_wallet_id = 'core:setup-id'
  assert.equal(
    component.computed.selectedCoreWallet.call(state).status,
    'setup'
  )
})

test('watchonly failure leaves core choices available without auto-selecting', async () => {
  const {component, state} = page({
    available: false,
    wallets: [],
    core_wallets: [{id: 'core-id', name: 'Savings', status: 'ready'}],
    message: 'Watchonly unavailable'
  })
  state.formDialog.data.extra.onchain_wallet_id = null
  await component.methods.loadOnchainWallets.call(state)
  assert.equal(component.computed.onchainWalletOptions.call(state).length, 1)
  assert.equal(state.onchainMessages[0], 'Watchonly unavailable')
  assert.equal(state.formDialog.data.extra.onchain_wallet_id, null)
  component.methods.createOnchainWallet.call(state)
  assert.equal(state.g.newWalletType, 'onchain')
  state.$router = {push: route => assert.equal(route.query.wal, 'core-id')}
  component.methods.openOnchainWallet.call(state, 'core-id')
})

test('invoice wallet choices exclude non-Lightning and receive-disabled wallets', () => {
  const {component, state} = page({})
  state.g.user.wallets = [
    {id: 'ln', walletType: 'lightning', canReceivePayments: true},
    {id: 'shared', walletType: 'lightning-shared', canReceivePayments: true},
    {id: 'readonly', walletType: 'lightning-shared', canReceivePayments: false},
    {id: 'chain', walletType: 'onchain', canReceivePayments: true},
    {id: 'fiat', walletType: 'fiat', canReceivePayments: true}
  ]
  state.g.user.walletOptions = state.g.user.wallets.map(wallet => ({
    value: wallet.id
  }))
  const choices = component.computed.lightningWalletOptions.call(state)
  assert.deepEqual(
    choices.map(wallet => wallet.value),
    ['ln', 'shared']
  )
})
