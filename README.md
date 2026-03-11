# Expense Bot

Telegram → Notion Expense Tracker with Auto-Create Database

## Features

- 📸 Receipt image upload → Extract merchant, amount, date → Save to Notion
- 📄 PDF statement upload (Chase) → Extract transactions → Save to Notion
- 🗄️ **Auto-create Notion database** if NOTION_DATABASE_ID is not provided
- 🔍 Duplicate detection against existing Notion entries
- 🏷️ Automatic categorization
- 💬 Telegram status messages

## Quick Start (No Manual Database Setup!)

1. Create Notion integration: https://www.notion.so/my-integrations
2. Create a blank page in Notion and share it with your integration
3. Copy the page ID (from URL) as NOTION_PARENT_PAGE_ID
4. Leave NOTION_DATABASE_ID empty - the bot will create the database automatically!

## Notion Database Schema

The bot auto-creates a database named "Transactions" with these properties:

| Property | Type | Description |
|----------|------|-------------|
| 이름 | Title | Merchant/Description |
| 날짜 | Date | Transaction date |
| 금액 | Number | Amount (USD) |
| 카테고리 | Select | Category (식비, 교통, 쇼핑, 수입, etc.) |
| 세부카테고리 | Select | Subcategory |
| 결제수단 | Select | Payment method (카드, 현금, Zelle, etc.) |
| 통화 | Select | Currency (USD, KRW, EUR, JPY) |
| 문서타입 | Select | Receipt or Statement |
| 신뢰도 | Number | Extraction confidence (0-1) |
| 검토필요 | Checkbox | Needs review |

## Environment Variables

### Required

- `TELEGRAM_BOT_TOKEN` - From @BotFather
- `NOTION_TOKEN` - Notion integration token
- `NOTION_PARENT_PAGE_ID` - Parent page for auto-created database

### Optional

- `NOTION_DATABASE_ID` - Existing database ID (if not provided, auto-creates)
- `OPENAI_API_KEY` - For enhanced OCR
- `RENDER_EXTERNAL_URL` - For webhook setup

## Setup Options

### Option 1: Auto-Create Database (Recommended)

```env
TELEGRAM_BOT_TOKEN=your_token
NOTION_TOKEN=your_token
NOTION_PARENT_PAGE_ID=your_page_id
# NOTION_DATABASE_ID=leave_empty
```

The bot will create a "Transactions" database under your parent page.

### Option 2: Use Existing Database

```env
TELEGRAM_BOT_TOKEN=your_token
NOTION_TOKEN=your_token
NOTION_DATABASE_ID=your_db_id
NOTION_PARENT_PAGE_ID=your_page_id
```

## Webhook Setup

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<URL>/webhook/telegram
```

## Supported Formats

- Receipt images (JPG, PNG)
- Receipt PDFs
- Chase bank statement PDFs

## Error Handling

The bot provides clear error messages for:
- Invalid Notion parent page (not shared with integration)
- Invalid Notion database (not shared with integration)
- Database creation failures
- PDF text extraction issues

## Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Deployment

### Render

1. Connect GitHub repo
2. Set environment variables
3. Deploy!

The database will be auto-created on first use.
