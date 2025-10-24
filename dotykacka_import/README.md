# Dotykacka Import for Odoo 18

One-way integration from Dotykačka POS → Odoo for importing orders, customers, products, invoices, and payments.

## Features

- **Webhook-based real-time synchronization** from Dotykacka to Odoo
- **OAuth 2.0 authentication** with Dotypos API v2
- **Automatic import** of:
  - Customers (res.partner)
  - Products (product.product)
  - Sales Orders (sale.order)
  - Invoices (account.move)
  - Payments (account.payment)
- **Order filtering** by location (on-site vs takeaway)
- **Automatic reconciliation** of payments with invoices
- **Cron fallback** for missed webhook events
- **Rate limit handling** (150 req/30 min)
- **Comprehensive logging** of all sync operations

## Installation

1. Install dependencies:
   ```bash
   pip install requests
   ```

2. Install the module:
   - Place `dotykacka_import` and `api_manager` modules in your Odoo addons directory
   - Update Apps List in Odoo
   - Search for "Dotykacka Import" and install it

## Configuration

### 1. OAuth Setup

1. Go to **Dotykacka → Configuration**
2. Create a new configuration
3. Fill in:
   - **Name**: Your configuration name
   - **Cloud ID**: Your Dotykacka Cloud ID
   - **OAuth Client ID**: From Dotykacka developer portal
   - **OAuth Client Secret**: From Dotykacka developer portal
   - **OAuth Redirect URI**: `https://your-odoo.com/dotykacka/oauth/callback`

4. Click **"Authorize OAuth"** button
5. Log in to Dotykacka and authorize the application
6. Tokens will be automatically saved

### 2. Webhook Registration

1. After OAuth authorization, click **"Register Webhooks"**
2. Webhooks will be automatically registered in Dotykacka
3. Your webhook URL: `https://your-odoo.com/dotykacka/webhook/{config_id}`

### 3. Payment Method Mapping

1. Go to **Dotykacka → Payment Methods**
2. Create mappings for each payment method:
   - **CASH** → Cash Journal
   - **CARD** → Bank Journal
   - **GLOVO** → Glovo Journal
   - etc.

### 4. Sync Settings

Configure auto-processing options:
- **Import On-Site Orders**: Import orders with location "on site"
- **Import Takeaway Orders**: Import orders with location "takeaway" (usually handled in KeyCRM)
- **Auto Confirm Orders**: Automatically confirm sales orders after import
- **Auto Create Invoice**: Automatically create and post invoices
- **Auto Register Payment**: Automatically register payments and reconcile with invoices

## Usage

### Automatic Sync (Webhooks)

Orders are automatically imported when:
- Order is created in Dotykacka
- Order is updated in Dotykacka
- Order is deleted in Dotykacka (triggers cancellation)

### Manual Sync

1. Go to **Dotykacka → Configuration**
2. Open your configuration
3. Click **"Sync Now"** button

### Cron Job

A cron job runs every 15 minutes to sync missed orders:
- Go to **Settings → Technical → Automation → Scheduled Actions**
- Find "Dotykacka: Sync Orders"
- Activate it if needed

## How It Works

### Order Creation Flow

```
Dotykacka Order Created
  ↓
Webhook Received
  ↓
Import/Update Customer
  ↓
Import/Update Products
  ↓
Create Sale Order
  ↓
Confirm Order (if enabled)
  ↓
Create Invoice (if enabled)
  ↓
Register Payments (if enabled)
  ↓
Reconcile with Invoice
```

### Order Deletion Flow

```
Dotykacka Order Deleted
  ↓
Webhook Received
  ↓
Find Related Sale Order
  ↓
Create Credit Note for Invoice
  ↓
Cancel Sale Order
```

## Monitoring

### Sync Logs

View all synchronization operations:
- Go to **Dotykacka → Sync Logs**
- Filter by:
  - Entity Type (Order, Customer, Product)
  - Status (Created, Updated, Error, Skipped)
  - Date

### Webhook Status

Check webhook activity:
- Go to **Dotykacka → Configuration**
- View "Webhooks" tab
- See trigger count and last triggered time

## Troubleshooting

### Connection Test Failed

1. Check OAuth tokens are valid
2. Click "Refresh Token" if expired
3. Verify Cloud ID is correct
4. Check network connectivity

### Orders Not Importing

1. Check webhook is registered
2. Verify webhook URL is accessible from internet
3. Check Sync Logs for errors
4. Verify order location matches import settings

### Payment Not Reconciling

1. Check payment method mapping exists
2. Verify journal is correct type (cash/bank)
3. Check invoice is posted
4. Review Sync Logs for reconciliation errors

## API Endpoints

### Webhook Endpoint

```
POST /dotykacka/webhook/{config_id}
Content-Type: application/json

{
  "event": "order.created",
  "data": {
    ...order data...
  }
}
```

### OAuth Callback

```
GET /dotykacka/oauth/callback?code=...&state=...
```

## Technical Details

### Dependencies

- `api_manager`: API request manager
- `sale`: Sales module
- `account`: Accounting module
- `product`: Product module

### Models

- `dotykacka.config`: Main configuration
- `dotykacka.oauth`: OAuth handler
- `dotykacka.webhook`: Webhook management
- `dotykacka.importer`: Import logic
- `dotykacka.sync.log`: Sync logging
- `dotykacka.payment.method`: Payment method mapping

### API Rate Limits

Dotykacka API has rate limits:
- **150 requests per 30 minutes**
- Module handles rate limiting automatically
- Cron job respects rate limits

## Support

For issues and questions:
- Check Sync Logs for error details
- Review Odoo server logs
- Contact GymBeam support

## License

AGPL-3

## Author

GymBeam - https://www.gymbeam.com
