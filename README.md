# Expense Bot

Telegram → Notion Expense Tracker

## Features

- 📸 Receipt image upload → Extract merchant, amount, date → Save to Notion
- 📄 PDF statement upload (Chase) → Extract transactions → Save to Notion
- 🔍 Duplicate detection against existing Notion entries
- 🏷️ Automatic categorization
- 💬 Telegram status messages

## Notion Database Schema

Required properties (Korean names):

| Property | Type | Description |
|----------|------|-------------|
| 이름 | Title | Merchant/Description |
| 날짜 | Date | Transaction date |
| 금액 | Number | Amount |
| 카테고리 | Select | Category |
| 세부카테고리 | Select | Subcategory |
| 결제수단 | Select | Payment method |
| 통화 | Select | Currency (USD/KRW) |
| 문서타입 | Select | Receipt or Statement |
| 신뢰도 | Number | Extraction confidence |
| 검토필요 | Checkbox | Needs review |

## Setup

1. Create Notion integration: https://www.notion.so/my-integrations
2. Create database with properties above
3. Share database with integration
4. Create Telegram bot via @BotFather
5. Copy `.env.example` to `.env` and fill values
6. Deploy to Render or run locally

## Environment Variables

- `TELEGRAM_BOT_TOKEN` - Required. From @BotFather
- `NOTION_TOKEN` - Required. Notion integration token
- `NOTION_DATABASE_ID` - Required. Database ID from URL
- `OPENAI_API_KEY` - Optional. For enhanced OCR
- `RENDER_EXTERNAL_URL` - Optional. For webhook setup

## Webhook Setup

Set Telegram webhook:
```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<URL>/webhook/telegram
```

## Supported Formats

- Receipt images (JPG, PNG)
- Receipt PDFs
- Chase bank statement PDFs

## Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
