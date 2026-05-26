# Shorts Finder — 배포 가이드

## 구조

```
shorts-finder/
├── backend/
│   ├── main.py          # FastAPI 서버 (핵심 로직)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx      # React UI
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   └── vite.config.js   # 빌드 → backend/static 으로 출력
├── Dockerfile
├── railway.toml
└── .gitignore
```

---

## 1. 로컬 실행 (개발)

### 백엔드
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 프론트엔드 (별도 터미널)
```bash
cd frontend
npm install
npm run dev     # http://localhost:5173 에서 실행
                # /api 요청은 localhost:8000으로 프록시됨
```

---

## 2. Railway 배포 (권장)

### 2-1. GitHub 저장소 푸시
```bash
cd shorts-finder
git init
git add .
git commit -m "init: Shorts Finder"
git remote add origin https://github.com/<your-id>/shorts-finder.git
git push -u origin main
```

### 2-2. Railway 프로젝트 생성
1. https://railway.app 접속 → New Project
2. **Deploy from GitHub repo** 선택
3. `shorts-finder` 저장소 선택
4. Railway가 `railway.toml`을 감지해 자동으로 Dockerfile 빌드

### 2-3. 배포 완료
- 도메인: `https://shorts-finder-xxxxx.up.railway.app`
- 헬스체크: `/api/health`

---

## 3. Render 배포 (대안)

1. https://render.com → New → Web Service
2. GitHub 저장소 연결
3. Environment: **Docker**
4. Dockerfile Path: `Dockerfile`
5. Start Command 비워두기 (Dockerfile CMD 사용)
6. **Create Web Service** 클릭

---

## 핵심 로직 — 채널 내 후보 영상 탐색 (문제 해결)

### 기존 문제
- 단순 플레이리스트 순회 → 관련 없는 영상 선택 ("바다간이야기")

### 해결 전략 (이중 탐색)

**1단계: YouTube Search API (채널 내 검색)**
```
GET /search?channelId=<id>&q=<keyword>&type=video
```
- 쇼츠 제목/태그에서 추출한 키워드 조합으로 채널 내 검색
- 여러 키워드 조합 병렬 검색 (단일 키워드 3개 + 조합 1개)

**2단계: 업로드 목록 전체 수집 (누락 보완)**
```
GET /playlistItems?playlistId=<uploads>&maxResults=50 (페이지네이션)
```
- 채널 전체 영상 최대 500개 수집
- 로컬에서 키워드 매칭 점수 계산

**스코어링 가중치**
| 위치 | 가중치 |
|------|--------|
| 제목 매칭 | 3x |
| 태그 매칭 | 2x |
| 설명 매칭 | 1x |

**신뢰도 기준**
| 등급 | 조건 |
|------|------|
| HIGH ✅ | 점수 ≥ 50% AND 매칭 키워드 ≥ 2개 |
| MEDIUM ⚡ | 점수 ≥ 25% OR 매칭 키워드 ≥ 1개 |
| LOW ❓ | 나머지 |

---

## API 엔드포인트

### POST /api/analyze
```json
{
  "shorts_url": "https://youtube.com/shorts/xxxxx",
  "api_key": "AIzaxxxxxxxx",
  "max_candidates": 10
}
```

응답:
```json
{
  "shorts_id": "xxxxx",
  "shorts_title": "코스트코 꿀잠템 베개 리뷰",
  "shorts_channel": "김강우",
  "extracted_keywords": ["코스트코", "베개", "꿀잠템", "바디필로우"],
  "candidates": [
    {
      "video_id": "yyyyy",
      "title": "[코스트코 쇼핑] 수면 최강 아이템 총정리",
      "url": "https://youtube.com/watch?v=yyyyy",
      "score": 0.833,
      "matched_keywords": ["코스트코", "베개"],
      "confidence": "HIGH",
      "thumbnail": "https://img.youtube.com/vi/yyyyy/mqdefault.jpg"
    }
  ],
  "total_searched": 147,
  "search_strategy": "Search API + 업로드 목록 병합"
}
```
