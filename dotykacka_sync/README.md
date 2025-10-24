# Dotykačka Sync

One-way integration from Dotykačka POS to Odoo 18.

## Features

### Event-Driven Synchronization
- **Webhook-based**: Real-time synchronization via Dotykačka webhooks
- **Cron fallback**: Automated sync every 15 minutes to catch missed events
- **OAuth 2.0**: Secure authentication with automatic token refresh

### Entity Synchronization
- **Customers** (res.partner): Create/update with full contact details
- **Products** (product.product): Upsert by SKU/barcode
- **Sales Orders** (sale.order): Create/update with order lines, discounts, taxes
- **Invoices** (account.move): Automatic invoice generation from orders
- **Payments** (account.payment): Multi-payment support with reconciliation

### Business Rules
- ✅ Import only orders with status "on site"
- ❌ Skip orders with status "takeaway"
- 🗑️ Handle order deletions (cancel orders, invoices, payments)
- 💰 Multiple payment methods mapped to Odoo journals
- 🔄 Automatic invoice validation and payment reconciliation

## Installation

1. Copy the `dotykacka_sync` module to your Odoo addons directory
2. Update the apps list
3. Install "Dotykačka Sync" module

## Configuration

### 1. OAuth Setup
1. Go to **Dotykačka → Configuration → Configurations**
2. Create a new configuration
3. Fill in:
   - **Cloud ID**: Your Dotykačka Cloud ID
   - **Client ID**: OAuth Client ID from Dotykačka
   - **Client Secret**: OAuth Client Secret from Dotykačka

### 2. Test Connection
1. Click "Test Connection" button
2. Verify authentication is successful

### 3. Register Webhooks
1. Click "Register Webhooks" button
2. This registers the following events:
   - `order.created`
   - `order.updated`
   - `order.deleted`

### 4. Configure Payment Methods
1. Go to "Payment Methods" tab
2. Map Dotykačka payment methods to Odoo journals
3. Supported payment types:
   - Cash
   - Card
   - Voucher
   - Online Payment
   - Glovo/Wolt

### 5. Sync Settings
Configure synchronization options:
- **Sync Customers**: Enable/disable customer sync
- **Sync Products**: Enable/disable product sync
- **Sync Orders**: Enable/disable order sync
- **Order Status Filter**: Choose which order types to import
- **Auto Create Invoices**: Automatically generate invoices
- **Auto Validate Invoices**: Automatically validate generated invoices
- **Auto Reconcile Payments**: Automatically reconcile payments to invoices

## Usage

### Manual Synchronization
Click "Sync Now" button on any configuration to manually trigger synchronization.

### Webhook URL
After creating a configuration, you'll see the webhook URL:
```
https://your-odoo-instance.com/dotykacka/webhook/{config_id}
```

Register this URL in Dotykačka's webhook settings.

### Monitoring
View sync logs at **Dotykačka → Logs** to monitor:
- API calls
- Webhook events
- Synchronization status
- Errors and warnings

## API Rate Limits

Dotykačka API has a limit of ~150 requests per 30 minutes. The module:
- Monitors rate limit headers
- Logs warnings when approaching limit
- Provides user-friendly error messages

## Technical Details

### Models
- `dotykacka.config`: Main configuration
- `dotykacka.oauth`: OAuth 2.0 handler
- `dotykacka.sync.log`: Synchronization logs
- `dotykacka.customer.sync`: Customer synchronization
- `dotykacka.product.sync`: Product synchronization
- `dotykacka.order.sync`: Order synchronization
- `dotykacka.invoice.sync`: Invoice generation
- `dotykacka.payment.sync`: Payment synchronization
- `dotykacka.payment.method`: Payment method mapping

### Controllers
- `/dotykacka/webhook/{config_id}`: Webhook receiver
- `/dotykacka/webhook/test`: Test endpoint

### Cron Jobs
- **Sync All Configurations**: Runs every 15 minutes
- **Cleanup Old Logs**: Runs daily (keeps logs for 30 days)

## Security

### Groups
- **Dotykačka Administrator**: Full access to all features
- **Dotykačka User**: Read-only access

### Webhook Security
- Optional webhook signature validation using HMAC-SHA256
- Public endpoint with configuration-level security

## Troubleshooting

### Connection Issues
1. Verify OAuth credentials are correct
2. Check token expiration date
3. Review sync logs for error details

### Webhook Not Receiving Events
1. Verify webhook URL is correctly registered in Dotykačka
2. Check that configuration is active
3. Test webhook endpoint: `/dotykacka/webhook/test`

### Synchronization Errors
1. Check sync logs for detailed error messages
2. Verify API rate limits are not exceeded
3. Ensure all required Odoo journals are configured

## Support

For issues or questions:
1. Check sync logs for error details
2. Review Dotykačka API documentation
3. Contact your Odoo administrator

## License

LGPL-3

## Credits

Developed for Odoo 18.0 using Dotykačka API v2.
