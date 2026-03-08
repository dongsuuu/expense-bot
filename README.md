# 💰 Expense Analysis Bot

Telegram 기반 지출 분석 및 Notion 연동 시스템

## 🎯 기능

- 📸 **영수증 사진** 분석
- 📄 **PDF 명세서** 처리
- 🧠 **AI 자동 분류** (카테고리/세부카테고리)
- 🔍 **중복 검출** (동일 지출 방지)
- 💡 **지출 피드백** 생성
- 📝 **Notion 자동 저장**
- 💬 **Telegram 결과 알림**

## 🏗️ 아키텍처

```
[사용자] → [Telegram] → [FastAPI]
                           ↓
              [OCR/추출] → [분류] → [중복검사]
                           ↓
              [Notion 저장] + [Telegram 응답]
```

## 🚀 설치

### 1. 클론

```bash
git clone https://github.com/yourusername/expense-bot.git
cd expense-bot
```

### 2. 가상환경

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 시스템 의존성 (Tesseract + Poppler)

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-kor poppler-utils
```

**macOS:**
```bash
brew install tesseract tesseract-lang poppler
```

**Windows:**
- Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
- Poppler: https://github.com/oschwartz10612/poppler-windows

### 5. 환경변수 설정

```bash
cp .env.example .env
# .env 파일 편집
```

## ⚙️ 설정

### 1. Telegram Bot 생성

1. @BotFather 에서 `/newbot`
2. 이름과 username 설정
3. **Bot Token** 복사 → `.env`의 `TELEGRAM_BOT_TOKEN`

### 2. Notion Integration

1. https://www.notion.so/my-integrations → New integration
2. **Internal Integration Token** 복사 → `.env`의 `NOTION_TOKEN`
3. Notion 페이지에서 Database 생성:
   - 이름: "지출 내역"
   - 속성:
     | 이름 | 타입 |
     |------|------|
     | 이름 | Title |
     | 날짜 | Date |
     | 금액 | Number |
     | 카테고리 | Select |
     | 세부카테고리 | Select |
     | 결제수단 | Select |
     | 통화 | Select |
     | 문서타입 | Select |
     | 신뢰도 | Number |
     | 검토필요 | Checkbox |
4. Database 공유 → Integration 추가
5. Database URL에서 **ID** 복사 → `.env`의 `NOTION_DATABASE_ID`

### 3. Webhook 설정 (배포 시)

```bash
# ngrok 로컬 테스트
ngrok http 8000

# Webhook 등록
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://your-ngrok-url/webhook/telegram"
```

## 🏃 실행

### 로컬 개발

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 배포 (GitHub Actions)

1. GitHub Secrets 설정:
   - `TELEGRAM_BOT_TOKEN`
   - `NOTION_TOKEN`
   - `NOTION_DATABASE_ID`
   - `OPENAI_API_KEY` (선택)

2. `.github/workflows/deploy.yml` 추가

## 📁 프로젝트 구조

```
expense-bot/
├── app/
│   ├── main.py                 # FastAPI 앱
│   ├── core/
│   │   └── config.py           # 설정
│   ├── routes/
│   │   └── telegram.py         # Webhook 핸들러
│   ├── services/
│   │   ├── extraction.py       # OCR/추출
│   │   ├── categorizer.py      # 카테고리 분류
│   │   ├── deduper.py          # 중복 검사
│   │   ├── feedback.py         # 피드백 생성
│   │   ├── notion_writer.py    # Notion 저장
│   │   └── telegram_sender.py  # Telegram 응답
│   ├── utils/
│   │   ├── telegram_files.py   # 파일 다운로드
│   │   └── pdf_utils.py        # PDF 처리
│   └── models/
│       └── schemas.py          # Pydantic 모델
├── requirements.txt
├── .env.example
└── README.md
```

## 🧪 테스트

```bash
# 영수증 이미지 테스트
curl -X POST "http://localhost:8000/webhook/telegram" \
  -H "Content-Type: application/json" \
  -d '{
    "update_id": 123,
    "message": {
      "chat": {"id": 123456789},
      "photo": [{"file_id": "test_file_id"}]
    }
  }'
```

## 🔮 향후 업그레이드

- [ ] 월간 지출 리포트
- [ ] 예산 설정 및 알림
- [ ] 영수증 이미지 저장 (S3)
- [ ] 다국어 지원
- [ ] 더 정확한 OCR (Google Vision API)

## 📄 라이선스

MIT
