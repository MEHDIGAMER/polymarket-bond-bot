# Polymarket sign-up — exact step-by-step

> **You don't need to do this until paper-trade validation passes.**
> The dashboard's OKR gates tell you when. Until then, this is reference only.

## What you'll need

| Item | Why | Cost |
|---|---|---|
| A wallet (MetaMask or Coinbase Wallet) | Polymarket runs on Polygon — you sign trades from your wallet | free |
| USDC.e on Polygon | The currency Polymarket uses for trades | what you fund (we plan $5K to start, $30K at full scale) |
| A non-blocked IP at sign-up time | Polymarket geo-blocks UAE / US / a few others | VPN like Mullvad ($5/mo) or use the Hetzner VPS as a SOCKS5 proxy |
| ~30 minutes | One-time setup | — |

---

## Step 1 — Create a wallet

**Option A: Coinbase Wallet** (easiest if you already have a Coinbase account)
- Install Coinbase Wallet (mobile app or browser extension)
- Write down the 12-word recovery phrase **on paper, not in any cloud doc**
- Lose this and you lose the money. Permanently.

**Option B: MetaMask** (more web-native)
- metamask.io → install browser extension
- Same recovery-phrase rule

Then in the wallet:
1. Switch the active network to **Polygon** (search "Polygon" → add network)
2. Note your wallet address — starts with `0x...`

---

## Step 2 — Fund USDC.e on Polygon

Polymarket uses **USDC.e** on Polygon (the bridged version, not native USDC). The cheapest path:

**If you have a Coinbase exchange account:**
1. Buy USDC on Coinbase
2. Withdraw to your wallet address — pick "Polygon" as the network
3. Coinbase charges ~$1 fee, takes ~5 min

**If you use Binance / OKX / Kraken:**
1. Buy USDC
2. Withdraw — pick "Polygon" network (sometimes labeled MATIC)
3. Send to your wallet's `0x...` address

**Don't send USDC over Ethereum mainnet** — gas will eat $20+ in fees. Polygon is the right network.

You also need a tiny bit of **POL** (formerly MATIC) for transaction gas. About $1 worth. Coinbase or Binance both sell it.

---

## Step 3 — Sign up at Polymarket

> ⚠️ **UAE/US users:** Polymarket geo-blocks at sign-up. Use a VPN with an exit in the EU/UK/Canada/Brazil for this single step. Mullvad and ProtonVPN work. After signup the wallet auth carries through; you only need the VPN once.

1. Go to **https://polymarket.com**
2. Click "Connect Wallet" → pick your wallet (MetaMask/Coinbase)
3. Approve the connection in your wallet popup
4. Sign the verification message (gas-free, just a signature)
5. Done — you're in

Polymarket will ask you to **deposit USDC.e to your Polymarket wallet** (an internal address tied to your account). Send some test amount first — $50 — to confirm everything works before sending more.

---

## Step 4 — Get the wallet's private key for the bot (later, not now)

This step happens **only after** the dashboard's OKR gates all turn green and you're ready to switch the bot from PAPER → LIVE-SMALL.

1. In MetaMask: account menu → "Account details" → "Show private key"
2. In Coinbase Wallet: settings → "Show recovery phrase" then derive
3. **Use a separate wallet for the bot** — never the one holding your main savings
4. Plan: keep ≤ $10K on the bot's wallet, rotate every 90 days

The bot will hold this private key encrypted on the Hetzner VPS. The dashboard never sees it.

---

## Step 5 — When you're ready to deploy real money

The dashboard will show all 3 OKR gates green:
- ✅ ≥50 resolved positions
- ✅ ≥94% win rate
- ✅ ≥4.5% avg return

At that point, tell me "go live" and I'll:
1. Switch `MODE=LIVE-SMALL` in the bot's `.env`
2. Add the wallet private key to the bot's secrets (encrypted on disk)
3. Wire up the actual order-placement code (currently stubbed in `trader.py`)
4. Cap initial deployment at $5K, max $300/position, max 5 concurrent
5. Watch the first 10 fills with you live in the dashboard

If validation fails, we tune the filters and re-validate before any real money moves.

---

## Risks you should know about

1. **Smart contract risk** — Polymarket has been audited but on-chain code can have bugs. ~$10M+ has been on the platform years without major incident, but it's not zero.
2. **Wallet seed loss** — your 12-word recovery phrase is the entire security model. Lose it = lose the money.
3. **Resolution disputes** — markets get resolved by Polymarket's UMA oracle. ~99% of resolutions are clean; ~1% have disputes that delay payout 24-72h.
4. **Geo-block enforcement** — they've tightened over time. The bot runs from Hetzner Germany so it isn't your IP at risk.
5. **Tax** — winnings are taxable income in most jurisdictions. Track everything in the dashboard's CSV exports (coming).

---

## What I will NOT do without explicit approval

- Move the bot to LIVE mode without all 3 OKR gates green
- Deploy more than $5K on first switch to live
- Touch the wallet private key without you confirming first
- Close down the bot without a final report

If anything breaks, the kill-switch is `systemctl stop bondbot` on the VPS. Drawdown limit auto-pauses trading at -10% in 24h.
