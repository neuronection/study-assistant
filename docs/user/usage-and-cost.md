# Usage and cost

**Settings → Data → Data & Cost** shows the model calls Study Assistant has made
this month and the prices used to estimate their cost. It is local: no
telemetry, no install ID and no reporting.

## What is recorded

Every AI call through the task funnel writes a local audit row: task, provider,
model, input/output tokens when the provider reports them, and the estimated
cost. Prompts and replies are not stored in this ledger. A call with missing
token counts is counted but shown as **unpriced**.

## Reading the page

- **Overview** shows the month total, calls and tokens per task.
- **Recent calls** lists the last 50 model calls with their cost provenance.
- **Prices** shows the effective built-in list price (with its checked date)
  and your custom prices. A custom row overrides a built-in row; remove it to
  return to the built-in price.

Built-in prices are standard-tier, uncached and non-batch estimates. They
exclude taxes, credits, negotiated rates, cached/batch discounts and regional
pricing. **Your provider bill is authoritative.** An unknown price stays
unpriced; the app does not fetch prices from vendors.

## Custom prices

A custom row can bind:

- a **provider key** (for example `openai`), or
- a **provider row id** for a custom provider that has no preset key.

Use the model id as the provider reports it, or choose **Prefix** to match
dated snapshots (for example `gpt-6.1-sol-`). Prices are USD per 1,000,000
tokens. Saving a row replaces the effective estimate for future calls only;
past calls keep the cost recorded at the time they happened.

Loopback/mDNS endpoints are free automatically. A local proxy can be priced
with an explicit provider row if it fronts a paid API.
