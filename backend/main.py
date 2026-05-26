"""
Shorts Finder Backend - FastAPI
YouTube Shorts → 원본 영상 구간 탐지 시스템
핵심: 채널 내 후보 영상 검색 정확도 개선
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import httpx
import re
import os
import math
from collections import Counter
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi.responses import JSONResponse
import traceback

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
    logger.error(f"Unhandled exception on {request.url}: {tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {str(exc)}"}
    )

# ─────────────────────────────────────────────
# 요청/응답 모델
# ─────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    shorts_url: str
    api_key: str
    max_candidates: Optional[int] = 10

class VideoCandidate(BaseModel):
    video_id: str
    title: str
    url: str
    published_at: str
    score: float
    matched_keywords: list[str]
    confidence: str  # "HIGH" | "MEDIUM" | "LOW"
    thumbnail: str

class AnalyzeResponse(BaseModel):
    shorts_id: str
    shorts_title: str
    shorts_channel: str
    shorts_channel_id: str
    extracted_keywords: list[str]
    candidates: list[VideoCandidate]
    total_searched: int
    search_strategy: str


# ─────────────────────────────────────────────
# YouTube URL 파싱
# ─────────────────────────────────────────────

def extract_video_id(url: str) -> Optional[str]:
    """YouTube URL에서 영상 ID 추출 (Shorts / 일반 영상 모두 지원)"""
    patterns = [
        r'youtube\.com/shorts/([A-Za-z0-9_-]{11})',
        r'youtube\.com/watch\?v=([A-Za-z0-9_-]{11})',
        r'youtu\.be/([A-Za-z0-9_-]{11})',
        r'^([A-Za-z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


# ─────────────────────────────────────────────
# 키워드 추출 (한국어 + 영어 혼합 지원)
# ─────────────────────────────────────────────

# 불용어 목록 (한국어/영어 공통)
STOPWORDS = {
    '이', '가', '을', '를', '의', '에', '는', '은', '와', '과',
    '로', '으로', '도', '만', '에서', '이다', '있다', '없다',
    '하다', '되다', '같다', '그', '이', '저', '것', '수', '때',
    '더', '아', '어', '잖', '죠', '죠', '요', '네', '나', '도',
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on',
    'at', 'to', 'for', 'of', 'and', 'or', 'but', 'with',
    'shorts', 'youtube', '유튜브', '쇼츠', 'short',
}

def extract_keywords(title: str, description: str = "", tags: list = None) -> list[str]:
    """
    제목/설명/태그에서 의미있는 키워드 추출
    전략:
    1. 해시태그 추출 (#코스트코 → 코스트코)
    2. 특수문자 제거 후 토큰화
    3. 불용어 제거
    4. 2글자 이상 단어만
    5. 빈도 기반 가중치
    """
    keywords = []
    all_text = f"{title} {description}"

    # 1. 해시태그 우선 추출 (높은 신뢰도)
    hashtags = re.findall(r'#([^\s#]+)', all_text)
    for tag in hashtags:
        clean_tag = re.sub(r'[^\w가-힣a-zA-Z0-9]', '', tag)
        if len(clean_tag) >= 2 and clean_tag.lower() not in STOPWORDS:
            keywords.append(clean_tag)

    # 2. 태그 목록 (API에서 가져온 경우)
    if tags:
        for tag in tags:
            clean = tag.strip()
            if len(clean) >= 2 and clean.lower() not in STOPWORDS:
                keywords.append(clean)

    # 3. 제목 토큰화 (한글 단어 / 영어 단어 분리)
    title_clean = re.sub(r'[^\w가-힣a-zA-Z0-9\s]', ' ', title)
    tokens = title_clean.split()
    for token in tokens:
        if len(token) >= 2 and token.lower() not in STOPWORDS:
            keywords.append(token)

    # 4. 설명에서 첫 200자 토큰화
    if description:
        desc_clean = re.sub(r'[^\w가-힣a-zA-Z0-9\s]', ' ', description[:200])
        desc_tokens = desc_clean.split()
        for token in desc_tokens:
            if len(token) >= 2 and token.lower() not in STOPWORDS:
                keywords.append(token)

    # 중복 제거 (순서 유지), 최대 20개
    seen = set()
    unique_keywords = []
    for kw in keywords:
        lower = kw.lower()
        if lower not in seen:
            seen.add(lower)
            unique_keywords.append(kw)

    return unique_keywords[:20]


# ─────────────────────────────────────────────
# 영상 스코어링 (TF-IDF 기반)
# ─────────────────────────────────────────────

def score_video(video: dict, keywords: list[str]) -> tuple[float, list[str]]:
    """
    키워드와 영상의 제목/태그/설명 매칭 점수 계산
    - 제목 매칭: 가중치 3x
    - 태그 매칭: 가중치 2x
    - 설명 매칭: 가중치 1x
    - 정확 일치 vs 부분 일치 구분
    """
    snippet = video.get('snippet', {})
    v_title = snippet.get('title', '').lower()
    v_description = snippet.get('description', '')[:300].lower()
    v_tags = [t.lower() for t in snippet.get('tags', [])]

    matched = []
    score = 0.0

    for kw in keywords:
        kw_lower = kw.lower()
        kw_score = 0.0

        # 제목 매칭 (가장 중요)
        if kw_lower in v_title:
            kw_score += 3.0
            if kw_lower not in matched:
                matched.append(kw)

        # 태그 매칭
        if any(kw_lower in tag or tag in kw_lower for tag in v_tags):
            kw_score += 2.0
            if kw_lower not in matched:
                matched.append(kw)

        # 설명 매칭
        if kw_lower in v_description:
            kw_score += 1.0
            if kw_lower not in matched:
                matched.append(kw)

        score += kw_score

    # 정규화: 키워드 수 대비 점수
    if keywords:
        score = score / (len(keywords) * 3.0)  # 최대 점수로 나눔

    return min(score, 1.0), matched


def get_confidence(score: float, matched_count: int) -> str:
    if score >= 0.5 and matched_count >= 2:
        return "HIGH"
    elif score >= 0.25 or matched_count >= 1:
        return "MEDIUM"
    else:
        return "LOW"


# ─────────────────────────────────────────────
# YouTube Data API 호출
# ─────────────────────────────────────────────

BASE_URL = "https://www.googleapis.com/youtube/v3"

async def get_video_info(video_id: str, api_key: str) -> dict:
    """영상 메타데이터 조회 (제목, 설명, 태그, 채널 ID)"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/videos",
                params={
                    "id": video_id,
                    "part": "snippet,contentDetails",
                    "key": api_key,
                }
            )
            if resp.status_code == 400:
                err = resp.json().get('error', {}).get('message', 'API 키 오류')
                raise HTTPException(status_code=400, detail=f"YouTube API 오류: {err}")
            elif resp.status_code == 403:
                raise HTTPException(status_code=403, detail="YouTube API 키가 유효하지 않거나 할당량이 초과되었습니다")
            resp.raise_for_status()
            data = resp.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"YouTube API 응답 오류: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube API 연결 실패: {str(e)}")

    if not data.get('items'):
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다. URL을 확인하세요.")
    return data['items'][0]


async def get_channel_uploads_playlist(channel_id: str, api_key: str) -> str:
    """채널의 업로드 재생목록 ID 조회"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/channels",
                params={
                    "id": channel_id,
                    "part": "contentDetails",
                    "key": api_key,
                }
            )
            resp.raise_for_status()
            data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"채널 정보 조회 실패: {str(e)}")

    if not data.get('items'):
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

    return data['items'][0]['contentDetails']['relatedPlaylists']['uploads']


async def get_all_channel_videos(playlist_id: str, api_key: str, max_pages: int = 10) -> list[dict]:
    """
    채널 업로드 재생목록에서 모든 영상 수집 (페이지네이션)
    max_pages * 50 = 최대 500개 영상까지
    """
    videos = []
    page_token = None

    async with httpx.AsyncClient(timeout=15) as client:
        for _ in range(max_pages):
            params = {
                "playlistId": playlist_id,
                "part": "snippet",
                "maxResults": 50,
                "key": api_key,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(f"{BASE_URL}/playlistItems", params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get('items', []):
                snippet = item.get('snippet', {})
                video_id = snippet.get('resourceId', {}).get('videoId')
                if video_id:
                    videos.append({
                        'id': video_id,
                        'snippet': snippet,
                    })

            page_token = data.get('nextPageToken')
            if not page_token:
                break

    return videos


async def search_channel_videos(channel_id: str, keywords: list[str], api_key: str) -> list[dict]:
    """
    YouTube Search API로 채널 내 키워드 검색
    전략: 키워드를 2~3개 조합으로 검색
    """
    results = {}

    # 키워드 조합 생성 (상위 5개)
    top_keywords = keywords[:5]
    search_queries = []

    # 단일 키워드 검색
    for kw in top_keywords[:3]:
        search_queries.append(kw)

    # 2개 조합 검색
    if len(top_keywords) >= 2:
        search_queries.append(f"{top_keywords[0]} {top_keywords[1]}")

    async with httpx.AsyncClient(timeout=15) as client:
        for query in search_queries:
            try:
                resp = await client.get(
                    f"{BASE_URL}/search",
                    params={
                        "channelId": channel_id,
                        "q": query,
                        "part": "snippet",
                        "type": "video",
                        "maxResults": 25,
                        "key": api_key,
                    }
                )
                resp.raise_for_status()
                data = resp.json()

                for item in data.get('items', []):
                    vid_id = item.get('id', {}).get('videoId')
                    if vid_id and vid_id not in results:
                        results[vid_id] = {
                            'id': vid_id,
                            'snippet': item.get('snippet', {}),
                        }
            except Exception as e:
                logger.warning(f"검색 실패 (쿼리: {query}): {e}")
                continue

    return list(results.values())


# ─────────────────────────────────────────────
# 메인 분석 엔드포인트
# ─────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze_shorts(req: AnalyzeRequest):
    """
    Shorts → 원본 영상 후보 탐색
    전략:
    1. Search API (채널 내 키워드 검색) - 빠르고 정확
    2. 업로드 목록 전체 수집 후 로컬 키워드 매칭 - 검색 누락 보완
    두 결과를 합쳐서 점수 순 정렬
    """
    try:
        # 1. Shorts ID 추출
        shorts_id = extract_video_id(req.shorts_url)
        if not shorts_id:
            raise HTTPException(status_code=400, detail="유효하지 않은 YouTube URL입니다")

        logger.info(f"분석 시작: {shorts_id}")

        # 2. Shorts 메타데이터 조회
        shorts_info = await get_video_info(shorts_id, req.api_key)
        snippet = shorts_info.get('snippet', {})
        channel_id = snippet.get('channelId', '')
        channel_title = snippet.get('channelTitle', '')
        shorts_title = snippet.get('title', '')
        shorts_desc = snippet.get('description', '')
        shorts_tags = snippet.get('tags', [])

        logger.info(f"채널: {channel_title} ({channel_id})")

        # 3. 키워드 추출
        keywords = extract_keywords(shorts_title, shorts_desc, shorts_tags)
        logger.info(f"추출된 키워드: {keywords}")

        if not keywords:
            raise HTTPException(status_code=400, detail="키워드를 추출할 수 없습니다. 제목/태그를 확인하세요.")

        # 4. 채널 업로드 재생목록 ID 조회
        try:
            uploads_playlist_id = await get_channel_uploads_playlist(channel_id, req.api_key)
        except Exception as e:
            logger.error(f"업로드 목록 조회 실패: {e}")
            uploads_playlist_id = None

        # 5. 두 가지 방법으로 후보 수집 (병렬)
        search_videos = []
        playlist_videos = []
        tasks = [search_channel_videos(channel_id, keywords, req.api_key)]
        if uploads_playlist_id:
            tasks.append(get_all_channel_videos(uploads_playlist_id, req.api_key))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        if not isinstance(results[0], Exception):
            search_videos = results[0]
            logger.info(f"Search API 결과: {len(search_videos)}개")
        else:
            logger.error(f"Search API 실패: {results[0]}")
        if len(results) > 1 and not isinstance(results[1], Exception):
            playlist_videos = results[1]
            logger.info(f"업로드 목록: {len(playlist_videos)}개")
        elif len(results) > 1:
            logger.error(f"업로드 목록 실패: {results[1]}")

        # 6. 중복 제거 후 통합
        all_videos = {}
        for v in search_videos + playlist_videos:
            vid = v.get('id') or v.get('snippet', {}).get('resourceId', {}).get('videoId', '')
            if vid and vid != shorts_id:
                all_videos[vid] = v

        total_searched = len(all_videos)
        logger.info(f"총 후보 풀: {total_searched}개")

        # 7. 스코어링
        scored = []
        for vid_id, video in all_videos.items():
            score, matched = score_video(video, keywords)
            if score > 0 or matched:
                confidence = get_confidence(score, len(matched))
                snippet_v = video.get('snippet', {})
                thumbnails = snippet_v.get('thumbnails', {})
                thumb = (
                    thumbnails.get('medium', {}).get('url') or
                    thumbnails.get('default', {}).get('url') or
                    f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg"
                )
                scored.append(VideoCandidate(
                    video_id=vid_id,
                    title=snippet_v.get('title', ''),
                    url=f"https://www.youtube.com