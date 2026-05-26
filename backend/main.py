"""
Shorts Finder Backend - FastAPI
YouTube Shorts -> 원본 영상 구간 탐지 시스템
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import httpx
import re
import traceback
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Shorts Finder API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    tb = traceback.format_exc()
    logger.error("Unhandled exception on %s: %s" % (request.url, tb))
    return JSONResponse(
        status_code=500,
        content={"detail": "%s: %s" % (type(exc).__name__, str(exc))}
    )

# ----------------------------------------
# 모델
# ----------------------------------------

class AnalyzeRequest(BaseModel):
    shorts_url: str
    api_key: str
    max_candidates: Optional[int] = 10

# ----------------------------------------
# 유틸
# ----------------------------------------

def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r'youtube\.com/shorts/([A-Za-z0-9_-]{11})',
        r'youtube\.com/watch\?v=([A-Za-z0-9_-]{11})',
        r'youtu\.be/([A-Za-z0-9_-]{11})',
        r'^([A-Za-z0-9_-]{11})$',
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None

STOPWORDS = {
    '이','가','을','를','의','에','는','은','와','과','로','으로','도','만','에서',
    '이다','있다','없다','하다','되다','그','것','수','때','더','요','나',
    'the','a','an','is','are','was','were','in','on','at','to','for','of',
    'and','or','but','with','shorts','youtube','short',
}

def extract_keywords(title: str, description: str = "", tags: list = None) -> list:
    keywords = []
    all_text = title + " " + description

    for tag in re.findall(r'#([^\s#]+)', all_text):
        clean = re.sub(r'[^\w가-힣a-zA-Z0-9]', '', tag)
        if len(clean) >= 2 and clean.lower() not in STOPWORDS:
            keywords.append(clean)

    if tags:
        for tag in tags:
            clean = tag.strip()
            if len(clean) >= 2 and clean.lower() not in STOPWORDS:
                keywords.append(clean)

    for token in re.sub(r'[^\w가-힣a-zA-Z0-9\s]', ' ', title).split():
        if len(token) >= 2 and token.lower() not in STOPWORDS:
            keywords.append(token)

    if description:
        for token in re.sub(r'[^\w가-힣a-zA-Z0-9\s]', ' ', description[:200]).split():
            if len(token) >= 2 and token.lower() not in STOPWORDS:
                keywords.append(token)

    seen = set()
    result = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            result.append(kw)
    return result[:20]


def score_video(video: dict, keywords: list) -> tuple:
    snippet = video.get('snippet', {})
    v_title = snippet.get('title', '').lower()
    v_desc = snippet.get('description', '')[:300].lower()
    v_tags = [t.lower() for t in snippet.get('tags', [])]

    matched = []
    score = 0.0
    for kw in keywords:
        kl = kw.lower()
        ks = 0.0
        if kl in v_title:
            ks += 3.0
            if kl not in matched:
                matched.append(kw)
        if any(kl in t or t in kl for t in v_tags):
            ks += 2.0
            if kl not in matched:
                matched.append(kw)
        if kl in v_desc:
            ks += 1.0
            if kl not in matched:
                matched.append(kw)
        score += ks

    if keywords:
        score = score / (len(keywords) * 3.0)
    return min(score, 1.0), matched


def get_confidence(score: float, matched_count: int) -> str:
    if score >= 0.5 and matched_count >= 2:
        return "HIGH"
    elif score >= 0.25 or matched_count >= 1:
        return "MEDIUM"
    return "LOW"


# ----------------------------------------
# YouTube API 호출
# ----------------------------------------

BASE_URL = "https://www.googleapis.com/youtube/v3"

async def get_video_info(video_id: str, api_key: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                BASE_URL + "/videos",
                params={"id": video_id, "part": "snippet,contentDetails", "key": api_key}
            )
            if resp.status_code == 403:
                raise HTTPException(status_code=403, detail="YouTube API 키가 유효하지 않거나 할당량이 초과되었습니다")
            if resp.status_code == 400:
                msg = resp.json().get('error', {}).get('message', '잘못된 요청')
                raise HTTPException(status_code=400, detail="YouTube API 오류: " + msg)
            resp.raise_for_status()
            data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail="YouTube API 연결 실패: " + str(e))

    if not data.get('items'):
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다. URL을 확인하세요.")
    return data['items'][0]


async def get_channel_uploads_playlist(channel_id: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                BASE_URL + "/channels",
                params={"id": channel_id, "part": "contentDetails", "key": api_key}
            )
            resp.raise_for_status()
            data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise Exception("채널 조회 실패: " + str(e))

    if not data.get('items'):
        raise Exception("채널 없음")
    return data['items'][0]['contentDetails']['relatedPlaylists']['uploads']


async def get_all_channel_videos(playlist_id: str, api_key: str, max_pages: int = 10) -> list:
    videos = []
    page_token = None
    async with httpx.AsyncClient(timeout=15) as client:
        for _ in range(max_pages):
            params = {"playlistId": playlist_id, "part": "snippet", "maxResults": 50, "key": api_key}
            if page_token:
                params["pageToken"] = page_token
            resp = await client.get(BASE_URL + "/playlistItems", params=params)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get('items', []):
                sn = item.get('snippet', {})
                vid = sn.get('resourceId', {}).get('videoId')
                if vid:
                    videos.append({'id': vid, 'snippet': sn})
            page_token = data.get('nextPageToken')
            if not page_token:
                break
    return videos


async def search_channel_videos(channel_id: str, keywords: list, api_key: str) -> list:
    results = {}
    top = keywords[:5]
    queries = [kw for kw in top[:3]]
    if len(top) >= 2:
        queries.append(top[0] + " " + top[1])

    async with httpx.AsyncClient(timeout=15) as client:
        for q in queries:
            try:
                resp = await client.get(
                    BASE_URL + "/search",
                    params={"channelId": channel_id, "q": q, "part": "snippet",
                            "type": "video", "maxResults": 25, "key": api_key}
                )
                resp.raise_for_status()
                for item in resp.json().get('items', []):
                    vid = item.get('id', {}).get('videoId')
                    if vid and vid not in results:
                        results[vid] = {'id': vid, 'snippet': item.get('snippet', {})}
            except Exception as e:
                logger.warning("검색 실패 (%s): %s" % (q, e))
    return list(results.values())


# ----------------------------------------
# 메인 엔드포인트
# ----------------------------------------

@app.post("/api/analyze")
async def analyze_shorts(req: AnalyzeRequest):
    try:
        shorts_id = extract_video_id(req.shorts_url)
        if not shorts_id:
            raise HTTPException(status_code=400, detail="유효하지 않은 YouTube URL입니다")

        logger.info("분석 시작: " + shorts_id)

        info = await get_video_info(shorts_id, req.api_key)
        sn = info.get('snippet', {})
        channel_id = sn.get('channelId', '')
        channel_title = sn.get('channelTitle', '')
        shorts_title = sn.get('title', '')
        shorts_desc = sn.get('description', '')
        shorts_tags = sn.get('tags', [])

        keywords = extract_keywords(shorts_title, shorts_desc, shorts_tags)
        logger.info("키워드: " + str(keywords))

        if not keywords:
            raise HTTPException(status_code=400, detail="키워드를 추출할 수 없습니다.")

        uploads_id = None
        try:
            uploads_id = await get_channel_uploads_playlist(channel_id, req.api_key)
        except Exception as e:
            logger.error("업로드 목록 실패: " + str(e))

        tasks = [search_channel_videos(channel_id, keywords, req.api_key)]
        if uploads_id:
            tasks.append(get_all_channel_videos(uploads_id, req.api_key))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        search_vids = gathered[0] if not isinstance(gathered[0], Exception) else []
        playlist_vids = gathered[1] if len(gathered) > 1 and not isinstance(gathered[1], Exception) else []

        logger.info("Search: %d, Playlist: %d" % (len(search_vids), len(playlist_vids)))

        all_videos = {}
        for v in search_vids + playlist_vids:
            vid = v.get('id') or v.get('snippet', {}).get('resourceId', {}).get('videoId', '')
            if vid and vid != shorts_id:
                all_videos[vid] = v

        scored = []
        for vid_id, video in all_videos.items():
            score, matched = score_video(video, keywords)
            if score > 0 or matched:
                sn_v = video.get('snippet', {})
                thumbs = sn_v.get('thumbnails', {})
                thumb = (thumbs.get('medium', {}).get('url') or
                         thumbs.get('default', {}).get('url') or
                         "https://img.youtube.com/vi/" + vid_id + "/mqdefault.jpg")
                scored.append({
                    "video_id": vid_id,
                    "title": sn_v.get('title', ''),
                    "url": "https://www.youtube.com/watch?v=" + vid_id,
                    "published_at": sn_v.get('publishedAt', '')[:10],
                    "score": round(score, 3),
                    "matched_keywords": matched,
                    "confidence": get_confidence(score, len(matched)),
                    "thumbnail": thumb,
                })

        scored.sort(key=lambda x: (x['score'], len(x['matched_keywords'])), reverse=True)

        return {
            "shorts_id": shorts_id,
            "shorts_title": shorts_title,
            "shorts_channel": channel_title,
            "shorts_channel_id": channel_id,
            "extracted_keywords": keywords,
            "candidates": scored[:req.max_candidates],
            "total_searched": len(all_videos),
            "search_strategy": "Search API + 업로드 목록 병합" if playlist_vids else "Search API",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("analyze_shorts 오류: " + traceback.format_exc())
        raise HTTPException(status_code=500, detail="%s: %s" % (type(e).__name__, str(e)))


# ----------------------------------------
# 헬스체크 + 정적 파일
# ----------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index = static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"message": "Shorts Finder API"}
