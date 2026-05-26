import { useState, useEffect, useRef } from 'react'
import styled, { keyframes, createGlobalStyle } from 'styled-components'

// ── API ──────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_URL || ''

async function analyzeShorts({ shortsUrl, apiKey, maxCandidates = 10 }) {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      shorts_url: shortsUrl,
      api_key: apiKey,
      max_candidates: maxCandidates,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `서버 오류 (${res.status})`)
  }
  return res.json()
}

// ── Animations ───────────────────────────────────────────────────
const fadeIn = keyframes`from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}`
const spin = keyframes`to{transform:rotate(360deg)}`
const pulse = keyframes`0%,100%{opacity:1}50%{opacity:.4}`

// ── Styled Components ────────────────────────────────────────────
const Wrap = styled.div`
  max-width: 860px;
  margin: 0 auto;
  padding: 24px 16px 80px;
`

const Header = styled.header`
  text-align: center;
  padding: 48px 0 36px;
`

const Logo = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
`

const LogoIcon = styled.div`
  width: 48px; height: 48px;
  background: var(--red);
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px;
`

const Title = styled.h1`
  font-size: clamp(22px, 4vw, 32px);
  font-weight: 700;
  letter-spacing: -0.5px;
`

const Subtitle = styled.p`
  color: var(--text2);
  font-size: 14px;
  margin-top: 6px;
`

const Card = styled.div`
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 16px;
  animation: ${fadeIn} .3s ease;
`

const Label = styled.label`
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: .5px;
  margin-bottom: 8px;
`

const Input = styled.input`
  width: 100%;
  background: var(--surface2);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  padding: 12px 14px;
  font-size: 15px;
  transition: border-color .2s;
  &:focus { border-color: var(--red); outline: none; }
  &::placeholder { color: #555; }
`

const Row = styled.div`
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
`

const Field = styled.div`
  flex: ${p => p.flex || 1};
  min-width: 200px;
`

const PasswordWrap = styled.div`
  position: relative;
  input { padding-right: 44px; }
`

const EyeBtn = styled.button`
  position: absolute;
  right: 12px; top: 50%;
  transform: translateY(-50%);
  background: none;
  color: var(--text2);
  font-size: 18px;
  line-height: 1;
  &:hover { color: var(--text); }
`

const AnalyzeBtn = styled.button`
  background: var(--red);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  padding: 12px 28px;
  border-radius: var(--radius-sm);
  white-space: nowrap;
  transition: background .2s, transform .1s;
  &:hover { background: var(--red-dim); }
  &:active { transform: scale(.97); }
  &:disabled { background: #333; color: #666; cursor: not-allowed; transform: none; }
`

const HintRow = styled.div`
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
`

const Hint = styled.button`
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 20px;
  color: var(--text2);
  font-size: 12px;
  padding: 4px 12px;
  transition: all .2s;
  &:hover { border-color: var(--red); color: var(--text); }
`

const Spinner = styled.div`
  width: 20px; height: 20px;
  border: 2px solid #333;
  border-top-color: var(--red);
  border-radius: 50%;
  animation: ${spin} .7s linear infinite;
  display: inline-block;
`

const StatusMsg = styled.p`
  font-size: 14px;
  color: var(--text2);
  animation: ${pulse} 1.5s ease infinite;
`

const ErrorBox = styled.div`
  background: #1a0000;
  border: 1px solid #5c0000;
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  color: #ff6b6b;
  font-size: 14px;
  animation: ${fadeIn} .3s ease;
`

const MetaCard = styled(Card)`
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: flex-start;
`

const MetaInfo = styled.div`
  flex: 1;
  min-width: 200px;
`

const MetaTitle = styled.h2`
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 6px;
  line-height: 1.3;
`

const MetaDetail = styled.p`
  font-size: 13px;
  color: var(--text2);
  margin-bottom: 4px;
`

const TagList = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
`

const Tag = styled.span`
  background: ${p => p.primary ? 'rgba(255,0,0,.15)' : 'var(--surface2)'};
  border: 1px solid ${p => p.primary ? 'rgba(255,0,0,.4)' : 'var(--border)'};
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  color: ${p => p.primary ? '#ff6666' : 'var(--text2)'};
`

const SectionTitle = styled.h3`
  font-size: 15px;
  font-weight: 700;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: .5px;
  margin: 24px 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
`

const Badge = styled.span`
  background: var(--surface2);
  border-radius: 20px;
  font-size: 12px;
  padding: 2px 8px;
  font-weight: 600;
`

const CandidateGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 14px;
`

const CandidateCard = styled.a`
  display: flex;
  gap: 14px;
  background: var(--surface);
  border: 1.5px solid ${p =>
    p.conf === 'HIGH' ? 'rgba(0,200,83,.35)' :
    p.conf === 'MEDIUM' ? 'rgba(255,214,0,.25)' :
    'var(--border)'};
  border-radius: var(--radius);
  padding: 14px;
  text-decoration: none;
  transition: border-color .2s, background .2s;
  animation: ${fadeIn} .35s ease both;
  animation-delay: ${p => p.delay}s;
  &:hover {
    border-color: ${p =>
      p.conf === 'HIGH' ? 'rgba(0,200,83,.7)' :
      p.conf === 'MEDIUM' ? 'rgba(255,214,0,.6)' :
      '#555'};
    background: var(--surface2);
  }
`

const Thumb = styled.div`
  flex-shrink: 0;
  width: 120px;
  height: 68px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--surface2);
  img {
    width: 100%; height: 100%;
    object-fit: cover;
  }
`

const CandInfo = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
`

const CandTitle = styled.p`
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`

const ConfBadge = styled.span`
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  background: ${p =>
    p.conf === 'HIGH' ? 'rgba(0,200,83,.2)' :
    p.conf === 'MEDIUM' ? 'rgba(255,214,0,.15)' :
    'rgba(255,255,255,.06)'};
  color: ${p =>
    p.conf === 'HIGH' ? 'var(--green)' :
    p.conf === 'MEDIUM' ? 'var(--yellow)' :
    'var(--text2)'};
  display: inline-block;
`

const ScoreBar = styled.div`
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  margin-top: 4px;
  overflow: hidden;
  div {
    height: 100%;
    width: ${p => p.score * 100}%;
    background: ${p =>
      p.conf === 'HIGH' ? 'var(--green)' :
      p.conf === 'MEDIUM' ? 'var(--yellow)' :
      '#555'};
    border-radius: 2px;
    transition: width 1s ease;
  }
`

const MatchedKws = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
`

const Kw = styled.span`
  font-size: 11px;
  background: rgba(33,150,243,.15);
  border: 1px solid rgba(33,150,243,.3);
  color: #64b5f6;
  border-radius: 3px;
  padding: 1px 6px;
`

const EmptyState = styled.div`
  text-align: center;
  padding: 48px 24px;
  color: var(--text2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
`

const RankNum = styled.span`
  font-size: 11px;
  font-weight: 700;
  color: ${p => p.rank === 1 ? '#ffd600' : p.rank === 2 ? '#bdbdbd' : p.rank === 3 ? '#bf8c5a' : 'var(--text2)'};
  display: block;
  margin-bottom: 2px;
`

// ── 예시 URL ──────────────────────────────────────────────────────
const EXAMPLES = [
  'https://www.youtube.com/shorts/tW0n0EQ-e0U',
  'https://youtube.com/shorts/4jKBm3Cq2Qk',
  'https://www.youtube.com/shorts/xyz_example',
]

// ── App Component ─────────────────────────────────────────────────
export default function App() {
  const [shortsUrl, setShortsUrl] = useState('')
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('yt_api_key') || '')
  const [showKey, setShowKey] = useState(false)
  const [loading, setLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const inputRef = useRef()

  useEffect(() => {
    if (apiKey) localStorage.setItem('yt_api_key', apiKey)
  }, [apiKey])

  const handleAnalyze = async () => {
    if (!shortsUrl.trim()) { inputRef.current?.focus(); return }
    if (!apiKey.trim()) { setError('YouTube API 키를 입력해주세요'); return }

    setLoading(true)
    setError('')
    setResult(null)

    const steps = [
      '쇼츠 메타데이터 분석 중…',
      '채널 업로드 목록 수집 중…',
      '키워드 매칭 검색 중…',
      '후보 영상 스코어링 중…',
    ]
    let stepIdx = 0
    setStatusMsg(steps[stepIdx])
    const timer = setInterval(() => {
      stepIdx = (stepIdx + 1) % steps.length
      setStatusMsg(steps[stepIdx])
    }, 2000)

    try {
      const data = await analyzeShorts({ shortsUrl, apiKey })
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      clearInterval(timer)
      setLoading(false)
      setStatusMsg('')
    }
  }

  const handleKey = e => e.key === 'Enter' && handleAnalyze()

  return (
    <Wrap>
      <Header>
        <Logo>
          <LogoIcon>🔍</LogoIcon>
          <Title>Shorts Finder</Title>
        </Logo>
        <Subtitle>YouTube Shorts → 원본 영상 구간 탐지 시스템</Subtitle>
      </Header>

      {/* 입력 카드 */}
      <Card>
        <Row>
          <Field flex={2}>
            <Label>YouTube Shorts URL</Label>
            <Input
              ref={inputRef}
              value={shortsUrl}
              onChange={e => setShortsUrl(e.target.value)}
              onKeyDown={handleKey}
              placeholder="https://youtube.com/shorts/..."
              spellCheck={false}
            />
          </Field>
          <Field>
            <Label>YouTube API Key</Label>
            <PasswordWrap>
              <Input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                onKeyDown={handleKey}
                placeholder="AIza..."
                spellCheck={false}
              />
              <EyeBtn type="button" onClick={() => setShowKey(v => !v)}>
                {showKey ? '🙈' : '👁️'}
              </EyeBtn>
            </PasswordWrap>
          </Field>
          <AnalyzeBtn onClick={handleAnalyze} disabled={loading}>
            {loading ? <Spinner /> : '분석 시작'}
          </AnalyzeBtn>
        </Row>

        {/* 예시 URL */}
        <HintRow>
          <span style={{ fontSize: 12, color: 'var(--text2)', alignSelf: 'center' }}>예시:</span>
          {EXAMPLES.map((url, i) => (
            <Hint key={i} onClick={() => setShortsUrl(url)}>
              예시 {i + 1}
            </Hint>
          ))}
        </HintRow>
      </Card>

      {/* 로딩 */}
      {loading && (
        <Card style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <Spinner />
          <StatusMsg>{statusMsg}</StatusMsg>
        </Card>
      )}

      {/* 에러 */}
      {error && <ErrorBox>⚠️ {error}</ErrorBox>}

      {/* 결과 */}
      {result && <Results result={result} />}

      {/* API 키 안내 */}
      {!result && !loading && (
        <ApiGuide />
      )}
    </Wrap>
  )
}

const ResultsWrap = styled.div`
  animation: ${fadeIn} .4s ease;
`

// ── Results ───────────────────────────────────────────────────────
function Results({ result }) {
  return (
    <ResultsWrap>
      {/* Shorts 정보 */}
      <MetaCard>
        <MetaInfo>
          <MetaDetail>📺 채널: {result.shorts_channel}</MetaDetail>
          <MetaTitle>{result.shorts_title}</MetaTitle>
          <MetaDetail style={{ marginTop: 4 }}>
            🔍 탐색 전략: {result.search_strategy} &nbsp;·&nbsp;
            📊 검색된 영상: {result.total_searched}개
          </MetaDetail>
          <TagList>
            <span style={{ fontSize: 12, color: 'var(--text2)', marginRight: 2 }}>추출 키워드:</span>
            {result.extracted_keywords.map((kw, i) => (
              <Tag key={i} primary={i < 5}>{kw}</Tag>
            ))}
          </TagList>
        </MetaInfo>
      </MetaCard>

      {/* 후보 목록 */}
      <SectionTitle>
        🎯 원본 영상 후보
        <Badge>{result.candidates.length}개</Badge>
      </SectionTitle>

      {result.candidates.length === 0 ? (
        <EmptyState>
          <p style={{ fontSize: 32, marginBottom: 12 }}>😕</p>
          <p>매칭된 후보 영상이 없습니다.</p>
          <p style={{ fontSize: 13, marginTop: 8 }}>
            키워드를 더 구체적으로 태그에 포함하거나, 채널 영상이 충분히 있는지 확인해보세요.
          </p>
        </EmptyState>
      ) : (
        <CandidateGrid>
          {result.candidates.map((c, i) => (
            <CandidateCard
              key={c.video_id}
              href={c.url}
              target="_blank"
              rel="noopener noreferrer"
              conf={c.confidence}
              delay={i * 0.05}
            >
              <Thumb>
                <img
                  src={c.thumbnail}
                  alt={c.title}
                  loading="lazy"
                  onError={e => { e.target.src = `https://img.youtube.com/vi/${c.video_id}/mqdefault.jpg` }}
                />
              </Thumb>
              <CandInfo>
                <RankNum rank={i + 1}>
                  {i === 0 ? '🥇 1위' : i === 1 ? '🥈 2위' : i === 2 ? '🥉 3위' : `#${i + 1}`}
                </RankNum>
                <CandTitle>{c.title}</CandTitle>
                {c.channel_title && (
                  <span style={{ fontSize: 11, marginBottom: 4, display: 'block' }}>
                    {c.is_source_channel && (
                      <span style={{ background: '#e53e3e', color: '#fff', fontSize: 10, padding: '1px 5px', borderRadius: 3, marginRight: 5 }}>출처</span>
                    )}
                    <span style={{ color: 'var(--text2)' }}>📺 {c.channel_title}</span>
                  </span>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                  <ConfBadge conf={c.confidence}>
                    {c.confidence === 'HIGH' ? '✅ 높음' : c.confidence === 'MEDIUM' ? '⚡ 보통' : '❓ 낮음'}
                  </ConfBadge>
                  <span style={{ fontSize: 12, color: 'var(--text2)' }}>
                    점수 {Math.round(c.score * 100)}%
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text2)', marginLeft: 'auto' }}>
                    {c.published_at}
                  </span>
                </div>
                <ScoreBar score={c.score} conf={c.confidence}><div /></ScoreBar>
                {c.matched_keywords.length > 0 && (
                  <MatchedKws>
                    {c.matched_keywords.slice(0, 5).map((kw, j) => (
                      <Kw key={j}>{kw}</Kw>
                    ))}
                  </MatchedKws>
                )}
              </CandInfo>
            </CandidateCard>
          ))}
        </CandidateGrid>
      )}
    </ResultsWrap>
  )
}

// ── API 가이드 ────────────────────────────────────────────────────
function ApiGuide() {
  return (
    <Card style={{ marginTop: 32, borderStyle: 'dashed' }}>
      <SectionTitle style={{ margin: '0 0 12px' }}>💡 YouTube API 키 발급 방법</SectionTitle>
      <ol style={{ color: 'var(--text2)', fontSize: 14, lineHeight: 2, paddingLeft: 20 }}>
        <li><a href="https://console.cloud.google.com" target="_blank" rel="noopener" style={{ color: 'var(--blue)' }}>Google Cloud Console</a> 접속 → 프로젝트 생성</li>
        <li>API 및 서비스 → 라이브러리 → <b style={{ color: 'var(--text)' }}>YouTube Data API v3</b> 검색 후 사용 설정</li>
        <li>사용자 인증 정보 → API 키 생성</li>
        <li>생성된 키를 위 입력란에 붙여넣기 (자동 저장됩니다)</li>
      </ol>
      <p style={{ marginTop: 12, fontSize: 12, color: '#555' }}>
        ※ API 키는 브라우저 로컬 스토리지에만 저장되며 서버로 전송됩니다 (분석 요청 시에만 사용).
      </p>
    </Card>
  )
}
