# Dotykačka Sync for Odoo 18

One-way integration from Dotykačka POS to Odoo 18.

## Features

- **Real-time synchronization** via webhooks
- **OAuth 2.0** authentication with automatic token refresh
- **Comprehensive sync**: Customers, Products, Orders, Invoices, Payments
- **Multiple payment methods**: Cash, Card, Wolt, Glovo, Foodora, Uber Eats
- **Smart filtering**: Import only "on site" orders (ignores "takeaway")
- **Deletion handling**: Automatic cancellation of orders, invoices, and payments
- **Rate limiting**: Respects Dotykačka API limits (~150 req/30 min)
- **Cron fallback**: Catches missed webhook events every 15 minutes

## Installation

1. Install dependency: `api_manager`
2. Install this module: `dotykacka_sync`
3. Configure in: **Dotykačka → Configuration**

## Configuration Steps

1. **OAuth Setup**
   - Enter Cloud ID, Client ID, Client Secret
   - Click "Authorize" to connect

2. **Payment Mapping**
   - Map Dotykačka payment methods to Odoo journals
   - Set one as default

3. **Webhook Registration**
   - Click "Register Webhook" for real-time sync

4. **Sync Settings**
   - Enable/disable customer, product, order sync
   - Configure order status filter

## How It Works

```
Dotykačka Order → Webhook → Odoo → Sale Order → Invoice → Payments
```

1. Order created in Dotykačka
2. Webhook event sent to Odoo
3. Module creates:
   - Customer (if new)
   - Products (if new)
   - Sale Order
   - Invoice
   - Payments (one per payment method)
   - Reconciles payments

## API Endpoints

- `/dotykacka/webhook/<cloud_id>` - Receives webhook events
- `/dotykacka/oauth/callback` - OAuth authorization callback

## Monitoring

View sync logs at **Dotykačka → Sync Logs**:
- Filter by type/status
- View error details
- Retry failed syncs

## Technical Details

- **API**: Dotypos API v2
- **Authentication**: OAuth 2.0 with refresh tokens
- **Sync Methods**: Webhooks (primary) + Cron (fallback)
- **Rate Limiting**: Built-in, respects API limits
- **Logging**: Comprehensive sync history

## Business Rules

- ✅ Imports "on site" orders
- ❌ Ignores "takeaway" orders (handled in KeyCRM)
- 🔄 Deleted orders → Cancel sale order, reverse invoice, cancel payments

## Requirements

- Odoo 18.0
- `api_manager` module
- Dotykačka account with API access
- OAuth credentials from Dotykačka

## License

LGPL-3

## Version

18.0.1.0.0
