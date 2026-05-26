"""
Shorts Finder Backend - FastAPI v2
YouTube Shorts -> 원본 영상 탐지 (출처 채널 우선 탐색)
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

app = FastAPI(title="Shorts Finder API", version="2.0.0")

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
    return JSONResponse(status_code=500, content={"detail": "%s: %s" % (type(exc).__name__, str(exc))})


class AnalyzeRequest(BaseModel):
    shorts_url: str
    api_key: str
    max_candidates: Optional[int] = 10


def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


STOPWORDS = {
    "이","가","을","를","의","에","는","은","와","과","로","으로","도","만","에서",
    "이다","있다","없다","하다","되다","그","것","수","때","더","요","나",
    "the","a","an","is","are","was","were","in","on","at","to","for","of",
    "and","or","but","with","shorts","youtube","short",
}


def extract_source_channels(title: str, description: str, tags: list = None) -> list:
    """설명/태그에서 출처 채널 힌트 추출 (@채널명, 출처:, 원본: 등)"""
    mentions = []
    combined = title + " " + description
    if tags:
        combined += " " + " ".join(tags)
    # @채널명 패턴
    for m in re.findall(r"@([\w\uAC00-\uD7A3A-Za-z0-9_.-]+)", combined):
        if len(m) >= 2:
            mentions.append(m)
    # 출처/원본 패턴 (한글)
    for m in re.finditer(r"출처[\s:]+([^\s\n#@]+)", combined):
        val = m.group(1).strip().rstrip(")")
        if len(val) >= 2:
            mentions.append(val)
    for m in re.finditer(r"원본[\s:]+([^\s\n#@]+)", combined):
        val = m.group(1).strip().rstrip(")")
        if len(val) >= 2:
            mentions.append(val)
    seen = set()
    result = []
    for m in mentions:
        if m.lower() not in seen:
            seen.add(m.lower())
            result.append(m)
    return result


def extract_keywords(title: str, description: str = "", tags: list = None) -> list:
    keywords = []
    all_text = title + " " + description
    for tag in re.findall(r"#([^\s#]+)", all_text):
        clean = re.sub(r"[^\w\uAC00-\uD7A3a-zA-Z0-9]", "", tag)
        if len(clean) >= 2 and clean.lower() not in STOPWORDS:
            keywords.append(clean)
    if tags:
        for tag in tags:
            clean = tag.strip()
            if len(clean) >= 2 and clean.lower() not in STOPWORDS:
                keywords.append(clean)
    for token in re.sub(r"[^\w\uAC00-\uD7A3a-zA-Z0-9\s]", " ", title).split():
        if len(token) >= 2 and token.lower() not in STOPWORDS:
            keywords.append(token)
    if description:
        for token in re.sub(r"[^\w\uAC00-\uD7A3a-zA-Z0-9\s]", " ", description[:200]).split():
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
    snippet = video.get("snippet", {})
    v_title = snippet.get("title", "").lower()
    v_desc = snippet.get("description", "")[:300].lower()
    v_tags = [t.lower() for t in snippet.get("tags", [])]
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
                msg = resp.json().get("error", {}).get("message", "잘못된 요청")
                raise HTTPException(status_code=400, detail="YouTube API 오류: " + msg)
            resp.raise_for_status()
            data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail="YouTube API 연결 실패: " + str(e))
    if not data.get("items"):
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")
    return data["items"][0]


async def get_channel_uploads_playlist(channel_id: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                BASE_URL + "/channels",
                params={"id": channel_id, "part": "contentDetails", "key": api_key}
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise Exception("채널 조회 실패: " + str(e))
    if not data.get("items"):
        raise Exception("채널 없음")
    return data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


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
            for item in data.get("items", []):
                sn = item.get("snippet", {})
                vid = sn.get("resourceId", {}).get("videoId")
                if vid:
                    videos.append({"id": vid, "snippet": sn})
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return videos


async def find_channel_id_by_name(channel_name: str, api_key: str) -> Optional[str]:
    """채널명으로 채널 ID 검색"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                BASE_URL + "/search",
                params={"q": channel_name, "part": "snippet",
                        "type": "channel", "maxResults": 3, "key": api_key}
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if items:
                return items[0].get("snippet", {}).get("channelId", "")
    except Exception as e:
        logger.warning("채널명 검색 실패 (%s): %s" % (channel_name, e))
    return None


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
                for item in resp.json().get("items", []):
                    vid = item.get("id", {}).get("videoId")
                    if vid and vid not in results:
                        results[vid] = {"id": vid, "snippet": item.get("snippet", {})}
            except Exception as e:
                logger.warning("채널 검색 실패 (%s): %s" % (q, e))
    return list(results.values())


@app.post("/api/analyze")
async def analyze_shorts(req: AnalyzeRequest):
    try:
        shorts_id = extract_video_id(req.shorts_url)
        if not shorts_id:
            raise HTTPException(status_code=400, detail="유효하지 않은 YouTube URL입니다")

        logger.info("분석 시작: " + shorts_id)
        info = await get_video_info(shorts_id, req.api_key)
        sn = info.get("snippet", {})
        channel_id = sn.get("channelId", "")
        channel_title = sn.get("channelTitle", "")
        shorts_title = sn.get("title", "")
        shorts_desc = sn.get("description", "")
        shorts_tags = sn.get("tags", [])

        keywords = extract_keywords(shorts_title, shorts_desc, shorts_tags)
        logger.info("키워드: " + str(keywords))
        if not keywords:
            raise HTTPException(status_code=400, detail="키워드를 추출할 수 없습니다.")

        # 1단계: 설명에서 출처 채널 힌트 추출
        source_mentions = extract_source_channels(shorts_title, shorts_desc, shorts_tags)
        logger.info("출처 힌트: " + str(source_mentions))

        # 2단계: 출처 채널 ID 검색
        source_channel_ids = []
        if source_mentions:
            ch_results = await asyncio.gather(
                *[find_channel_id_by_name(m, req.api_key) for m in source_mentions[:3]],
                return_exceptions=True
            )
            for ch_id in ch_results:
                if ch_id and not isinstance(ch_id, Exception) and ch_id not in ("", channel_id):
                    if ch_id not in source_channel_ids:
                        source_channel_ids.append(ch_id)
        logger.info("출처 채널 IDs: " + str(source_channel_ids))

        # 3단계: 출처 채널 업로드 목록 (전체 영상)
        source_playlist_ids = []
        if source_channel_ids:
            pl_results = await asyncio.gather(
                *[get_channel_uploads_playlist(ch_id, req.api_key) for ch_id in source_channel_ids],
                return_exceptions=True
            )
            for pl_id in pl_results:
                if pl_id and not isinstance(pl_id, Exception):
                    source_playlist_ids.append(pl_id)

        # 4단계: 쇼츠 채널 업로드 목록
        uploads_id = None
        try:
            uploads_id = await get_channel_uploads_playlist(channel_id, req.api_key)
        except Exception as e:
            logger.error("업로드 목록 실패: " + str(e))

        # 5단계: 병렬 검색
        tasks = []
        for src_id in source_channel_ids:
            tasks.append(search_channel_videos(src_id, keywords, req.api_key))
        for pl_id in source_playlist_ids:
            tasks.append(get_all_channel_videos(pl_id, req.api_key))
        tasks.append(search_channel_videos(channel_id, keywords, req.api_key))
        if uploads_id:
            tasks.append(get_all_channel_videos(uploads_id, req.api_key))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        all_vids_list = []
        for r in gathered:
            if not isinstance(r, Exception):
                all_vids_list.extend(r)
        logger.info("총 수집: %d" % len(all_vids_list))

        # 6단계: 중복 제거 + 점수 계산
        all_videos = {}
        for v in all_vids_list:
            vid = v.get("id") or v.get("snippet", {}).get("resourceId", {}).get("videoId", "")
            if vid and vid != shorts_id:
                all_videos[vid] = v

        scored = []
        for vid_id, video in all_videos.items():
            score, matched = score_video(video, keywords)
            if score > 0 or matched:
                sn_v = video.get("snippet", {})
                thumbs = sn_v.get("thumbnails", {})
                thumb = (thumbs.get("medium", {}).get("url") or
                         thumbs.get("default", {}).get("url") or
                         "https://img.youtube.com/vi/" + vid_id + "/mqdefault.jpg")
                scored.append({
                    "video_id": vid_id,
                    "title": sn_v.get("title", ""),
                    "url": "https://www.youtube.com/watch?v=" + vid_id,
                    "channel_title": sn_v.get("channelTitle", ""),
                    "published_at": sn_v.get("publishedAt", "")[:10],
                    "score": round(score, 3),
                    "matched_keywords": matched,
                    "confidence": get_confidence(score, len(matched)),
                    "thumbnail": thumb,
                })

        scored.sort(key=lambda x: (x["score"], len(x["matched_keywords"])), reverse=True)

        strategy_parts = []
        if source_channel_ids:
            strategy_parts.append("출처채널(" + ",".join(source_mentions[:2]) + ")")
        strategy_parts.append("쇼츠채널")

        return {
            "shorts_id": shorts_id,
            "shorts_title": shorts_title,
            "shorts_channel": channel_title,
            "shorts_channel_id": channel_id,
            "extracted_keywords": keywords,
            "source_mentions": source_mentions,
            "candidates": scored[:req.max_candidates],
            "total_searched": len(all_videos),
            "search_strategy": " + ".join(strategy_parts),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("오류: " + traceback.format_exc())
        raise HTTPException(status_code=500, detail="%s: %s" % (type(e).__name__, str(e)))


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


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
