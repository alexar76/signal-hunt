import { lazy, Suspense, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { api, ApiError, clearSession, ensureSession } from './api';
import { formatMessage, type Locale } from './i18n';
import type { Evidence, HeroEvent, LeaderboardEntry, PlayerProfile, Reward, Round, Verdict } from './types';

const languages: Locale[] = ['en', 'ru', 'es', 'fr', 'zh'];
const tierCodes = ['stargazer', 'pathfinder', 'signal_analyst', 'void_navigator', 'constellation_keeper', 'federation_oracle'];
const badgeCodes = [
  'first_contact', 'calibrated_mind', 'deep_scan', 'clean_vector', 'minimal_evidence',
  'triple_lock', 'seasoned_observer', 'perfect_orbit', 'dual_lock', 'streak_keeper',
  'season_polyglot', 'season_hunter', 'season_prime_runner',
];
const FederationField = lazy(() => import('./FederationField'));
const githubRoot = 'https://github.com/alexar76/signal-hunt';
const githubDocsRoot = 'https://github.com/alexar76/signal-hunt/blob/main/docs';
const documentSuffix: Record<Locale, string> = { en: '', ru: '.ru', es: '.es', fr: '.fr', zh: '.zh' };

// Live progress toward a still-locked cumulative relic. Single-round predicates
// (Brier, evidence count, one-round score) have no meaningful partial state and return null.
function badgeProgress(code: string, profile: PlayerProfile): { current: number; target: number } | null {
  const season = profile.season;
  let raw: { current: number; target: number } | null = null;
  switch (code) {
    case 'triple_lock': raw = { current: profile.current_streak, target: 3 }; break;
    case 'seasoned_observer': raw = { current: profile.rounds, target: 5 }; break;
    case 'streak_keeper': raw = { current: profile.daily_streak ?? 0, target: 3 }; break;
    case 'season_polyglot': raw = season ? { current: season.distinct_diagnoses.length, target: season.targets.polyglot } : null; break;
    case 'season_hunter': raw = season ? { current: season.score, target: season.targets.hunter } : null; break;
    case 'season_prime_runner': raw = season ? { current: season.prime_corrects, target: season.targets.prime_runner } : null; break;
    default: return null;
  }
  if (!raw || raw.current <= 0) return null;
  return { current: Math.min(raw.current, raw.target), target: raw.target };
}

function compactHost(value: string): string {
  try { return new URL(value).host + new URL(value).pathname.replace(/\/$/, ''); } catch { return value; }
}

function EvidenceData({ evidence }: { evidence: Evidence }) {
  const data = evidence.data;
  const kind = String(data.kind || '');

  if (kind === 'peer_roster' || (Array.isArray(data.peers) && Array.isArray(data.left_peer_urls))) {
    const peers = (data.peers as Record<string, unknown>[]) || [];
    const left = (data.left_peer_urls as string[]) || [];
    return (
      <div className="evidence-rows">
        {data.joined_count != null && (
          <div className="evidence-row"><span>joined</span><strong>{String(data.joined_count)}</strong></div>
        )}
        {data.left_count != null && (
          <div className="evidence-row"><span>left</span><strong>{String(data.left_count)}</strong></div>
        )}
        {peers.map((peer) => {
          const label = compactHost(String(peer.url || peer.name || '?'));
          return (
            <div className="evidence-row" key={`p-${label}`}>
              <span>{label}{peer.roster ? ` · ${String(peer.roster)}` : ''}</span>
              <strong>{peer.capabilities_count != null ? String(peer.capabilities_count) : '—'}</strong>
            </div>
          );
        })}
        {left.map((url) => (
          <div className="evidence-row" key={`l-${url}`}>
            <span>{compactHost(url)} · left</span>
            <strong>—</strong>
          </div>
        ))}
      </div>
    );
  }

  if (kind === 'latency_surface' || (Array.isArray(data.peers) && data.threshold_ms != null)) {
    const peers = (data.peers as Record<string, unknown>[]) || [];
    return (
      <div className="evidence-rows">
        {(['threshold_ms', 'slow_count', 'measured_count', 'max_ms', 'median_ms'] as const).map((key) => (
          data[key] != null ? (
            <div className="evidence-row" key={key}>
              <span>{key.replaceAll('_', ' ')}</span>
              <strong>{String(data[key])}</strong>
            </div>
          ) : null
        ))}
        {peers.map((peer) => {
          const label = compactHost(String(peer.url || peer.name || '?'));
          const ms = peer.latency_ms != null ? `${Math.round(Number(peer.latency_ms))} ms` : String(peer.probe_status || '—');
          return (
            <div className="evidence-row" key={label}>
              <span>{label}</span>
              <strong>{ms}</strong>
            </div>
          );
        })}
      </div>
    );
  }

  if (Array.isArray(data.sources)) {
    return <div className="evidence-rows">{(data.sources as Record<string, unknown>[]).map((source) => (
      <div className="evidence-row" key={String(source.id)}>
        <span>{compactHost(String(source.id))}</span><strong>{String(source.capabilities)}</strong>
      </div>
    ))}</div>;
  }

  if (kind === 'effective_pricing' || data.current != null || data.baseline_median_usd != null) {
    const current = (data.current && typeof data.current === 'object')
      ? data.current as Record<string, unknown>
      : null;
    const rows: Array<[string, unknown]> = [];
    if (current) {
      for (const key of ['min_usd', 'median_usd', 'max_usd']) {
        if (current[key] != null) rows.push([`current ${key}`, current[key]]);
      }
    }
    for (const key of ['baseline_median_usd', 'sample_size']) {
      if (data[key] != null) rows.push([key, data[key]]);
    }
    const hist = data.historical_medians_usd;
    if (Array.isArray(hist) && hist.length) {
      rows.push(['historical medians', hist.map(String).join(', ')]);
    }
    if (rows.length) {
      return <div className="evidence-rows">{rows.map(([key, value]) => (
        <div className="evidence-row" key={key}><span>{String(key).replaceAll('_', ' ')}</span><strong>{value == null ? '—' : String(value)}</strong></div>
      ))}</div>;
    }
  }

  if (Array.isArray(data.peers)) {
    return <div className="evidence-rows">{(data.peers as Record<string, unknown>[]).map((peer) => {
      const label = compactHost(String(peer.url || peer.name || '?'));
      const detail = peer.latency_ms != null
        ? `${Math.round(Number(peer.latency_ms))} ms`
        : (peer.capabilities_count != null ? String(peer.capabilities_count) : String(peer.probe_status || peer.roster || '—'));
      return (
        <div className="evidence-row" key={label}>
          <span>{label}{peer.roster ? ` · ${String(peer.roster)}` : ''}</span>
          <strong>{detail}</strong>
        </div>
      );
    })}</div>;
  }

  return <div className="evidence-rows">{Object.entries(data).filter(([, value]) => !Array.isArray(value) && typeof value !== 'object').map(([key, value]) => (
    <div className="evidence-row" key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value == null ? '—' : String(value)}</strong></div>
  ))}</div>;
}

export default function App() {
  const initialLocale = ((localStorage.getItem('signal-hunt-locale') || navigator.language.slice(0, 2)) as Locale);
  const [locale, setLocale] = useState<Locale>(languages.includes(initialLocale) ? initialLocale : 'en');
  const [session, setSession] = useState<{ token: string; handle: string } | null>(null);
  const [round, setRound] = useState<Round | null>(null);
  const [evidence, setEvidence] = useState<Record<string, Evidence>>({});
  const [selected, setSelected] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [confidence, setConfidence] = useState(0.6);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [weeklyBoard, setWeeklyBoard] = useState<{ week_id: string; entries: LeaderboardEntry[] } | null>(null);
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [heroes, setHeroes] = useState<HeroEvent[]>([]);
  const [handleDraft, setHandleDraft] = useState('');
  const [publicDraft, setPublicDraft] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  const [rewardBurst, setRewardBurst] = useState<Reward[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [broadcasting, setBroadcasting] = useState(false);
  const [broadcastDone, setBroadcastDone] = useState(false);
  const [shareCopied, setShareCopied] = useState(false);
  const [error, setError] = useState('');
  const [nowMs, setNowMs] = useState(() => Date.now());
  const loadStarted = useRef(false);
  const t = (key: string, params: Record<string, unknown> = {}) => formatMessage(locale, key, params);

  const followUpLabel = (option: string) => {
    const key = `followUp.option.${option}`;
    const labeled = t(key);
    return labeled === key ? compactHost(option) : labeled;
  };

  const load = async () => {
    setLoading(true); setError('');
    try {
      let active = session || await ensureSession();
      let live: Round;
      try {
        live = await api.live(active.token);
      } catch (cause) {
        if (!(cause instanceof ApiError) || cause.status !== 401) throw cause;
        clearSession();
        active = await ensureSession();
        live = await api.live(active.token);
      }
      setSession(active);
      const openedIds = Array.isArray(live.opened_evidence) ? live.opened_evidence : [];
      const restored: Record<string, Evidence> = {};
      if (openedIds.length) {
        await Promise.all(openedIds.map(async (evidenceId) => {
          try {
            restored[evidenceId] = await api.evidence(active.token, live.id, evidenceId);
          } catch {
            /* keep closed in UI if a block cannot be re-fetched */
          }
        }));
      }
      setEvidence(restored);
      setSelected('');
      setFollowUp('');
      setBroadcastDone(Boolean(live.verdict && !live.broadcast_available && (live.verdict.score || 0) >= 950));
      const [board, weekly, player, heroFeed] = await Promise.all([
        api.leaderboard(), api.weeklyLeaderboard(), api.profile(active.token), api.heroes(),
      ]);
      setRound(live); setVerdict(live.verdict || null); setLeaderboard(board.entries);
      setWeeklyBoard(weekly);
      setProfile(player); setHandleDraft(player.handle); setPublicDraft(player.public_profile);
      setHeroes(heroFeed.payload.events);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (loadStarted.current) return;
    loadStarted.current = true;
    void load();
  }, []);
  useEffect(() => { document.documentElement.lang = locale; localStorage.setItem('signal-hunt-locale', locale); }, [locale]);
  useEffect(() => {
    if (rewardBurst.length === 0) return;
    const timer = window.setTimeout(() => setRewardBurst([]), 3200);
    return () => window.clearTimeout(timer);
  }, [rewardBurst]);
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const manifestLive = round?.observation.sources_status.manifest?.status === 'ok';
  const signalRevealed = Boolean(round && !round.signal.sealed && round.signal.code);
  const signalTitle = round
    ? (signalRevealed
      ? t(`signal.${round.signal.code}.title`, round.signal.params || {})
      : t('missionSealedTitle'))
    : '';
  const signalBody = round
    ? (signalRevealed
      ? t(`signal.${round.signal.code}.body`, round.signal.params || {})
      : t('missionSealedBody'))
    : '';
  const severityLabel = round
    ? (round.signal.severity === 'calm' ? t('labelCalm') : t('labelAnomaly'))
    : '';
  const expiresMs = round ? Date.parse(round.expires_at) : NaN;
  const remainingMs = Number.isFinite(expiresMs) ? expiresMs - nowMs : 0;
  const roundExpired = Number.isFinite(expiresMs) && remainingMs <= 0;
  const clockLabel = useMemo(() => {
    if (!Number.isFinite(expiresMs)) return '—';
    const total = Math.max(0, Math.floor(remainingMs / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  }, [expiresMs, remainingMs]);
  const formatCountdown = (iso?: string | null) => {
    if (!iso) return '—';
    const ms = Date.parse(iso) - nowMs;
    if (!Number.isFinite(ms)) return '—';
    const total = Math.max(0, Math.floor(ms / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  };
  const observationTime = useMemo(() => round ? new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(round.observation.observed_at)) : '—', [round, locale]);
  const guideUrl = `${githubDocsRoot}/GUIDE${documentSuffix[locale]}.md`;
  const rulesUrl = `${githubDocsRoot}/RULES${documentSuffix[locale]}.md`;
  const showBroadcast = Boolean(verdict && verdict.score >= 950);

  const openEvidence = async (id: string) => {
    if (!session || !round || evidence[id]) return;
    try {
      const item = await api.evidence(session.token, round.id, id);
      setEvidence((current) => ({ ...current, [id]: item }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  };

  const submit = async () => {
    if (!session || !round || !selected) return;
    setSubmitting(true); setError(''); setShareCopied(false); setBroadcastDone(false);
    try {
      const result = await api.submit(session.token, round.id, selected, confidence, followUp || null);
      setVerdict(result);
      setRewardBurst(result.progression?.new_rewards || []);
      if (result.progression?.profile) setProfile(result.progression.profile);
      const [board, weekly, heroFeed, refreshed] = await Promise.all([
        api.leaderboard(), api.weeklyLeaderboard(), api.heroes(), api.live(session.token),
      ]);
      setRound(refreshed);
      setLeaderboard(board.entries);
      setWeeklyBoard(weekly);
      setHeroes(heroFeed.payload.events);
      setBroadcastDone(Boolean(
        !result.broadcast_available
        && result.score >= 950
        && Boolean(result.progression?.profile?.public_profile ?? profile?.public_profile),
      ));
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setSubmitting(false); }
  };

  const broadcastOrbit = async () => {
    if (!session || !round || !verdict) return;
    if (!profile?.public_profile) {
      setError(t('broadcastNeedPublic'));
      document.getElementById('heroes')?.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    setBroadcasting(true); setError('');
    try {
      const result = await api.broadcast(session.token, round.id);
      setBroadcastDone(true);
      setVerdict({ ...verdict, broadcast_available: false });
      if (result.event) {
        const heroFeed = await api.heroes();
        setHeroes(heroFeed.payload.events);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBroadcasting(false); }
  };

  const copyShareCard = async () => {
    if (!round || !verdict) return;
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const text = [
      `Signal Hunt · ${verdict.correct ? 'explained' : 'rejected'}`,
      `diagnosis=${verdict.answer}`,
      `round=${round.id}`,
      `observation=${round.observation.state_hash}`,
      `score=${verdict.score}`,
      `brier=${verdict.scoring.brier.toFixed(4)}`,
      `commitment=${round.answer_commitment}`,
      origin ? `play=${origin}/#mission` : '',
    ].filter(Boolean).join('\n');
    try {
      if (typeof navigator.share === 'function') {
        await navigator.share({ title: 'Signal Hunt', text });
        setShareCopied(true);
      } else {
        await navigator.clipboard.writeText(text);
        setShareCopied(true);
      }
      window.setTimeout(() => setShareCopied(false), 2400);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') return;
      try {
        await navigator.clipboard.writeText(text);
        setShareCopied(true);
        window.setTimeout(() => setShareCopied(false), 2400);
      } catch (fallback) {
        setError(fallback instanceof Error ? fallback.message : String(fallback));
      }
    }
  };

  const saveProfile = async () => {
    if (!session) return;
    setProfileSaving(true); setProfileSaved(false); setError('');
    try {
      const next = await api.updateProfile(session.token, handleDraft, publicDraft);
      setProfile(next); setProfileSaved(true);
      setSession({ ...session, handle: next.handle });
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setProfileSaving(false); }
  };

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#top" aria-label="AICOM Signal Hunt">
        <span className="brand-mark"><i /><i /><i /></span>
        <span><strong>{t('brand')}</strong><small>{t('node')}</small></span>
      </a>
      <nav className="site-nav" aria-label={t('nav')}>
        <a href="#how">{t('navHow')}</a>
        <a href="#mission">{t('navPlay')}</a>
        <a href="#heroes">{t('navRanks')}</a>
        <a href={guideUrl} target="_blank" rel="noreferrer">{t('navDocs')} ↗</a>
      </nav>
      <div className="top-actions">
        <span className={`live-pill ${manifestLive ? 'is-live' : ''}`}><i />{manifestLive ? t('live') : t('offline')}</span>
        <div className="languages" aria-label={t('language')}>{languages.map((language) => <button className={locale === language ? 'active' : ''} onClick={() => setLocale(language)} key={language}>{language === 'zh' ? '中文' : language.toUpperCase()}</button>)}</div>
      </div>
    </header>

    <main id="top">
      <section className="hero-grid">
        <div className="hero-copy">
          <div className="eyebrow"><span />{t('eyebrow')}</div>
          <h1>{t('hero')}<br /><em>{t('heroAccent')}</em></h1>
          <p className="lead">{t('lead')}</p>
          <div className="hero-actions">
            {round && <button className="primary-button" onClick={() => document.getElementById('mission')?.scrollIntoView({ behavior: 'smooth' })}>{t('start')}<span>↘</span></button>}
            <a className="secondary-button" href="#how">{t('learnRules')}<span>↓</span></a>
          </div>
          <div className="hero-trust" aria-label={t('proofLayer')}>
            <span><i />ED25519</span><span><i />{t('trustBrier')}</span><span><i />{t('trustLive')}</span>
          </div>
          <p className="truth-line">{t('realOnly')}</p>
        </div>
        <div className="field-card">
          <div className="field-scanline" />
          <Suspense fallback={<div className="field-loading" />}>
            <FederationField sources={round?.observation.sources || []} />
          </Suspense>
          <div className="field-overlay field-top"><span>{round?.observation.hub_name || 'SIGNAL HUNT HUB'}</span><b>{round ? compactHost(round.observation.hub_url) : '—'}</b></div>
          {round && <div className={`field-overlay field-assist ${round.federation_assist.status === 'ok' ? 'ok' : ''}`}>
            <span>{t('assist')}</span>
            <b>{round.federation_assist.status === 'ok' ? t('assistOk') : t('assistUnavailable')}</b>
            <small>{round.federation_assist.capability_id}{round.federation_assist.source_hub ? ` · ${compactHost(round.federation_assist.source_hub)}` : ''}</small>
          </div>}
          <div className="field-overlay field-bottom"><span>{t('stateHash')}</span><b>{round?.observation.state_hash.slice(0, 16) || '—'}</b></div>
          <div className="orbit-hint">{t('orbitHint')}</div>
        </div>
      </section>

      {loading && <section className="loading-panel"><div className="radar-loader" />{t('loading')}</section>}
      {error && !round && <section className="error-panel"><strong>{t('dataError')}</strong><span>{error}</span><button onClick={load}>{t('retry')}</button></section>}

      {round && <>
        <section className="telemetry-strip" aria-label={t('telemetryRegion')}>
          <article><span>{t('external')}</span><strong>{round.observation.capabilities.external}</strong><small>{t('cap')}</small></article>
          <article><span>{t('sources')}</span><strong>{round.observation.source_count}</strong><small>{t('hub')}</small></article>
          <article><span>{t('local')}</span><strong>{round.observation.capabilities.local}</strong><small>Signal Hunt</small></article>
          <article><span>{t('manifestLatency')}</span><strong>{round.observation.sources_status.manifest.elapsed_ms ?? '—'}</strong><small>{round.observation.sources_status.manifest.elapsed_ms == null ? '' : 'ms'}</small></article>
          <article className="wide"><span>{t('observation')}</span><strong>{observationTime}</strong><small>{round.observation.id}</small></article>
        </section>

        {(round.prime || round.engagement) && (
          <section className="engagement-strip" aria-label="engagement">
            {round.prime && (
              <article className={`prime-banner ${(round.prime.locked_for_round || round.prime.window_active) ? 'is-hot' : ''}`}>
                <small>
                  {round.prime.locked_for_round
                    ? t('primeLocked')
                    : round.prime.window_active
                      ? t('primeActive')
                      : t('primeNext', { clock: formatCountdown(round.prime.next_starts_at) })}
                </small>
                <strong>{round.prime.locked_for_round ? `×${round.prime.multiplier}` : '×1'}</strong>
                <p>
                  {round.prime.locked_for_round
                    ? t('primeHelp', { multiplier: round.prime.multiplier })
                    : round.prime.window_active
                      ? t('primeWindowOnly', { multiplier: round.prime.window_multiplier ?? 1.5 })
                      : t('primeHelp', { multiplier: 1.5 })}
                </p>
                {round.prime.window_active && round.prime.ends_at && <span>{formatCountdown(round.prime.ends_at)}</span>}
              </article>
            )}
            {round.engagement && (
              <article className="presence-banner">
                <span>{t('presenceLive', { count: round.engagement.presence.active_observers })}</span>
                <span>{t('presenceSolved', { count: round.engagement.presence.solved_this_round })}</span>
              </article>
            )}
          </section>
        )}

        <section className="explainer-section" id="how">
          <div className="section-heading"><span>00 / {t('labelProtocol')}</span><h2>{t('howTitle')}</h2></div>
          <div className="explainer-intro"><p>{t('howLead')}</p><a href={rulesUrl} target="_blank" rel="noreferrer">{t('fullRules')} ↗</a></div>
          <div className="protocol-track">
            {[
              ['01', '⌁', 'stepObserve', 'stepObserveBody'],
              ['02', '◎', 'stepInvestigate', 'stepInvestigateBody'],
              ['03', '◇', 'stepCommit', 'stepCommitBody'],
              ['04', '✦', 'stepVerify', 'stepVerifyBody'],
            ].map(([number, icon, title, body]) => <article key={number}>
              <small>{number}</small><div className="protocol-icon">{icon}<i /></div><h3>{t(title)}</h3><p>{t(body)}</p>
            </article>)}
          </div>
          <div className="proof-rail">
            <article><span>{t('proofCommit')}</span><strong>SHA-256</strong><p>{t('proofCommitBody')}</p></article>
            <article><span>{t('proofScore')}</span><strong>B = Σ(p−o)²</strong><p>{t('proofScoreBody')}</p></article>
            <article><span>{t('proofSocial')}</span><strong>OPT-IN · ED25519</strong><p>{t('proofSocialBody')}</p></article>
          </div>
        </section>

        {profile && <section className="progression-section" id="heroes">
          <div className="section-heading"><span>00 / {t('labelAscension')}</span><h2>{t('progression')}</h2></div>
          <div className="progression-grid">
            <article className="status-orbit-card" style={{ '--tier-accent': profile.tier.accent } as CSSProperties}>
              <div className="cosmic-status-orbit">
                <i className="orbit-ring orbit-ring-a" /><i className="orbit-ring orbit-ring-b" /><i className="orbit-ring orbit-ring-c" />
                <div className="status-core"><small>{t('status')}</small><strong>{t(`tier.${profile.tier.code}`)}</strong><span>{profile.score}</span></div>
                <span className="orbit-moon moon-a" /><span className="orbit-moon moon-b" /><span className="orbit-moon moon-c" />
              </div>
              <div className="status-progress-copy">
                <span>{profile.next_tier ? t('nextStatus') : t('maxStatus')}</span>
                <strong>{profile.next_tier ? t(`tier.${profile.next_tier.code}`) : t(`tier.${profile.tier.code}`)}</strong>
                <div className="status-progress"><i style={{ width: `${profile.tier_progress * 100}%` }} /></div>
                <small>{profile.next_tier ? `${profile.score} / ${profile.next_tier.min_score}` : `${profile.score} · MAX`}</small>
              </div>
              <div className="status-statline">
                <span><b>{profile.rounds}</b>{t('roundsPlayed')}</span>
                <span><b>{profile.accuracy == null ? '—' : `${Math.round(profile.accuracy * 100)}%`}</b>{t('accuracy')}</span>
                <span><b>{profile.best_streak}</b>{t('bestStreak')}</span>
                <span><b>{profile.daily_streak ?? 0}</b>{t('dailyStreak')}</span>
              </div>
              {profile.daily_streak_meta && (
                <div className={`streak-chip ${profile.daily_streak_meta.alive ? 'alive' : ''}`}>
                  {profile.daily_streak_meta.alive
                    ? (profile.daily_streak_meta.shield_available ? t('streakShield') : t('streakShieldUsed'))
                    : t('streakDead')}
                </div>
              )}
              {profile.season && (
                <div className="season-passport">
                  <small>{t('seasonPassport')}</small>
                  <strong>{t('seasonWeek', { week: profile.season.week_id })}</strong>
                  <div className="season-meters">
                    <span><b>{profile.season.score}</b>{t('seasonScore')}</span>
                    <span><b>{profile.season.distinct_diagnoses.length}/{profile.season.targets.polyglot}</b>{t('seasonDiagnoses')}</span>
                    <span><b>{profile.season.prime_corrects}/{profile.season.targets.prime_runner}</b>{t('seasonPrime')}</span>
                  </div>
                </div>
              )}
            </article>

            <article className="identity-card">
              <div className="identity-constellation"><i /><i /><i /><i /><span /></div>
              <small>DIOSCURI // {t('labelHeroRelay')}</small>
              <h3>{t('heroIdentity')}</h3>
              <p>{t('heroIdentityHelp')}</p>
              <label><span>{t('callSign')}</span><input value={handleDraft} maxLength={24} onChange={(event) => { setHandleDraft(event.target.value); setProfileSaved(false); }} /></label>
              <label className="broadcast-consent"><input type="checkbox" checked={publicDraft} onChange={(event) => { setPublicDraft(event.target.checked); setProfileSaved(false); }} /><span><b>{t('broadcastOptIn')}</b><small>{t('broadcastHelp')}</small></span></label>
              <button onClick={saveProfile} disabled={profileSaving}>{profileSaving ? t('saving') : profileSaved ? t('saved') : t('saveIdentity')}</button>
              <div className={`relay-status ${profile.public_profile ? 'armed' : ''}`}><i />{profile.public_profile ? t('relayArmed') : t('relayPrivate')}</div>
            </article>
          </div>

          <div className="tier-constellation" aria-label={t('statusPath')}>
            {tierCodes.map((code, index) => {
              const active = tierCodes.indexOf(profile.tier.code) >= index;
              return <div className={active ? 'active' : ''} key={code}><i><span>{index + 1}</span></i><strong>{t(`tier.${code}`)}</strong></div>;
            })}
          </div>

          <div className="vault-heading"><div><small>{t('labelPrizes')}</small><h3>{t('rewardVault')}</h3></div><p>{t('rewardTruth')}</p></div>
          <div className="reward-vault">
            {badgeCodes.map((code) => {
              const reward = profile.rewards.find((item) => item.code === code);
              const meta = reward || { code, kind: 'badge', rarity: code === 'perfect_orbit' ? 'legendary' : 'rare', sigil: code === 'perfect_orbit' ? '✦' : '◇' } as Reward;
              const progress = reward ? null : badgeProgress(code, profile);
              return <article className={`reward-sigil rarity-${meta.rarity} ${reward ? 'unlocked' : 'locked'} ${progress ? 'has-progress' : ''}`} key={code}>
                <div className="sigil-space"><i /><i /><i /><span>{meta.sigil}</span></div>
                <small>{reward ? t('unlocked') : t('locked')}</small><strong>{t(`badge.${code}`)}</strong><p>{t(`badge.${code}.help`)}</p>
                {progress && <div className="relic-progress" role="progressbar" aria-valuenow={progress.current} aria-valuemax={progress.target}>
                  <div className="relic-progress-bar"><i style={{ width: `${Math.min(100, (progress.current / progress.target) * 100)}%` }} /></div>
                  <b>{progress.current.toLocaleString()} / {progress.target.toLocaleString()}</b>
                </div>}
              </article>;
            })}
          </div>

          <div className="heroes-wall">
            <div className="heroes-title"><span>{t('labelHeroFeed')}</span><h3>{t('heroes')}</h3><p>{t('heroesHelp')}</p></div>
            <div className="hero-transmissions">{heroes.length === 0 ? <p className="muted">{t('noHeroes')}</p> : heroes.map((hero) => <article key={hero.id}>
              <div className="hero-star"><i /><span>✦</span></div><div><small>{t(`heroEvent.${hero.event_type}`).toUpperCase()}</small><strong>{hero.handle}</strong><span>{t(`tier.${hero.status}`)} · {hero.score}</span></div><code>{hero.id.slice(-8)}</code>
            </article>)}</div>
          </div>
        </section>}

        <section className="mission-section" id="mission">
          <div className="section-heading"><span>01 / {t('labelTrace')}</span><h2>{t('mission')}</h2></div>
          <div className="mission-grid">
            <article className={`signal-card severity-${round.signal.severity}`}>
              <div className="signal-meta">
                <span>{t('round')} {round.id}</span>
                <span className={`severity ${round.signal.sealed ? 'sealed' : ''}`}>
                  {round.signal.sealed ? t('labelSealed') : severityLabel}
                </span>
              </div>
              <div className="round-clock" aria-live="polite">
                <span>{t('roundClock')}</span>
                <strong>{roundExpired ? t('roundExpired') : t('roundEndsIn', { clock: clockLabel })}</strong>
                {roundExpired && <button type="button" onClick={() => void load()}>{t('nextRound')}</button>}
              </div>
              <div className="signal-radar"><i /><i /><i /></div>
              <h3>{signalTitle}</h3><p>{signalBody}</p>
              {typeof round.signal.history_depth === 'number' && (
                <p className="mission-history">{t('missionHistory', { count: round.signal.history_depth })}</p>
              )}
              <div className="commitment"><span>{t('commitment')}</span><code>{round.answer_commitment}</code><small>{t('commitmentHelp')}</small></div>
            </article>
            <article className="sources-card">
              <div className="card-label">{t('labelSourceField')}</div>
              {round.observation.sources.length === 0 && <p className="muted">{t('noHistory')}</p>}
              {round.observation.sources.map((source, index) => <div className="source-row" key={source.id}>
                <span className="source-index">{String(index + 1).padStart(2, '0')}</span>
                <div><strong>{compactHost(source.id)}</strong><span>{source.capabilities} {t('cap')}</span></div>
                <div className="share-bar"><i style={{ width: `${(source.share || 0) * 100}%` }} /></div>
                <b>{source.share == null ? '—' : `${(source.share * 100).toFixed(1)}%`}</b>
              </div>)}
            </article>
          </div>
        </section>

        <section className="investigate-section">
          <div className="section-heading"><span>02 / {t('labelEvidence')}</span><h2>{t('evidence')}</h2></div>
          <div className="evidence-grid">{round.evidence.map((item) => {
            const opened = evidence[item.id];
            return <article className={`evidence-card ${opened ? 'is-open' : ''}`} key={item.id}>
              <div className="evidence-icon">{
                item.id === 'distribution' ? '◌'
                : item.id === 'change' ? '↗'
                : item.id === 'pricing' ? '◇'
                : item.id === 'roster' ? '⬡'
                : item.id === 'latency' ? '⚡'
                : '⌁'
              }</div>
              <h3>{t(item.id)}</h3><small>{t(`evidenceKind.${item.kind}`)}</small>
              {opened ? <EvidenceData evidence={opened} /> : <button onClick={() => openEvidence(item.id)}>{t('open')} <span>−5%</span></button>}
            </article>;
          })}</div>
        </section>

        <section className="verdict-section">
          <div className="section-heading"><span>03 / {t('labelCommit')}</span><h2>{t('diagnosis')}</h2></div>
          {!verdict ? <div className="verdict-console">
            <div className="verdict-main">
              <div className="options">{round.options.map((option, index) => <button className={selected === option ? 'selected' : ''} onClick={() => setSelected(option)} key={option}>
                <span>{String.fromCharCode(65 + index)}</span><strong>{t(`diagnosis.${option}`)}</strong><i />
              </button>)}</div>
              {round.follow_up && (
                <div className="follow-up-panel">
                  <div className="follow-up-heading">
                    <small>{t('followUpTitle')}</small>
                    <strong>{t(round.follow_up.prompt)}</strong>
                    <p>{t('followUpHelp')}</p>
                  </div>
                  <div className="follow-up-options">
                    {round.follow_up.options.map((option) => (
                      <button
                        type="button"
                        className={followUp === option ? 'selected' : ''}
                        key={option}
                        onClick={() => setFollowUp(option)}
                      >
                        {followUpLabel(option)}
                      </button>
                    ))}
                    <button type="button" className={!followUp ? 'selected muted' : 'muted'} onClick={() => setFollowUp('')}>
                      {t('followUpSkip')}
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div className="confidence-panel"><div><span>{t('confidence')}</span><strong>{Math.round(confidence * 100)}%</strong></div>
              <input type="range" min="0.25" max="1" step="0.05" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} aria-label={t('confidence')} />
              <button className="submit-button" disabled={!selected || submitting} onClick={submit}>{submitting ? t('submitting') : t('submit')}<span>→</span></button>
              {!selected && <small>{t('choose')}</small>}
            </div>
          </div> : <div className={`result-card ${verdict.correct ? 'correct' : 'incorrect'}`}>
            {rewardBurst.length > 0 && <div className="reward-burst" aria-live="polite">
              {Array.from({ length: 18 }, (_, index) => <i key={index} style={{ '--spark': index } as CSSProperties} />)}
              <small>{t('newReward')}</small><strong>{rewardBurst.find((item) => item.kind === 'badge')
                ? t(`badge.${rewardBurst.find((item) => item.kind === 'badge')!.code}`)
                : t(`tier.${rewardBurst[0].code.replace('tier:', '')}`)}</strong>
            </div>}
            <div className="result-seal"><span>{verdict.correct ? '✓' : '×'}</span><i /></div>
            <div className="result-copy"><small>{t('result')}</small><h3>{verdict.correct ? t('correct') : t('incorrect')}</h3><p>{t('answer')}: <strong>{t(`diagnosis.${verdict.answer}`)}</strong></p><p className="hash-note">{t('verifyHash')}</p></div>
            <div className="score-block">
              <span>{t('score')}</span>
              <strong>{verdict.score}</strong>
              <small>
                {typeof verdict.scoring.base_score === 'number' && (
                  <>{t('scoreBase')} {verdict.scoring.base_score}</>
                )}
                {Boolean(verdict.scoring.follow_up_bonus) && (
                  <> · {t('scoreBonus')} +{verdict.scoring.follow_up_bonus}</>
                )}
                {verdict.scoring.prime_active && (
                  <> · {t('scorePrime')} ×{verdict.scoring.prime_multiplier}</>
                )}
              </small>
            </div>
            <div className="math-block"><span>{t('brier')} <b>{verdict.scoring.brier.toFixed(4)}</b></span><span>{t('skill')} <b>{(verdict.scoring.skill * 100).toFixed(1)}%</b></span><span>{t('evidenceFactor')} <b>{verdict.scoring.evidence_factor.toFixed(2)}</b></span></div>
            {verdict.follow_up && (
              <div className="follow-up-result">
                <span>{t('followUpResult')}</span>
                <strong>
                  {!verdict.follow_up.answered
                    ? t('followUpSkipped')
                    : verdict.follow_up.correct
                      ? t('followUpHit', { bonus: verdict.follow_up.bonus })
                      : t('followUpMiss')}
                </strong>
              </div>
            )}
            {(verdict.cliffhanger || round.engagement?.cliffhanger) && (
              <div className="cliffhanger-card">
                <small>{t('cliffhangerTitle')}</small>
                <strong>{t('cliffhangerTeaser')}</strong>
                <span>{t('cliffhangerOpens', { clock: formatCountdown((verdict.cliffhanger || round.engagement?.cliffhanger)?.next_opens_at) })}</span>
              </div>
            )}
            <div className="next-step-card">
              <small>{t('nextStepLabel')}</small>
              <strong>{t('nextStepTitle')}</strong>
              <p>{t('nextStepBody')}</p>
              <div className="next-step-actions">
                <a href={`${round.observation.hub_url}/ai-market/v2/manifest`} target="_blank" rel="noreferrer">{t('nextStepManifest')} ↗</a>
                <a href="https://use.modelmarket.dev/" target="_blank" rel="noreferrer">{t('nextStepPortal')} ↗</a>
              </div>
            </div>
            <div className="share-card">
              <p>{t('shareHelp')}</p>
              <div className="share-actions">
                <button type="button" onClick={() => void copyShareCard()}>{shareCopied ? t('shareCopied') : t('shareVerdict')}</button>
                {showBroadcast && (
                  <button
                    type="button"
                    className="broadcast-button"
                    disabled={broadcasting || Boolean(broadcastDone || (profile?.public_profile && !verdict.broadcast_available))}
                    onClick={() => void broadcastOrbit()}
                  >
                    {broadcasting
                      ? t('broadcasting')
                      : (broadcastDone || (profile?.public_profile && !verdict.broadcast_available))
                        ? t('broadcastDone')
                        : t('broadcastOrbit')}
                  </button>
                )}
              </div>
            </div>
          </div>}
          {error && <p className="inline-error">{error}</p>}
        </section>

        <section className="leaderboard-section">
          <div className="section-heading"><span>04 / {t('labelVerified')}</span><h2>{t('leaderboard')}</h2></div>
          <div className="leaderboard-card">{leaderboard.length === 0 ? <p className="muted">{t('emptyBoard')}</p> : leaderboard.map((entry) => <div className="leader-row" key={`${entry.rank}-${entry.handle}`}>
            <span>#{String(entry.rank).padStart(2, '0')}</span><strong>{entry.handle}<em>{t(`tier.${entry.tier}`)}</em></strong><small>{entry.correct}/{entry.rounds}</small><b>{entry.score}</b>
          </div>)}</div>
          {weeklyBoard && (
            <div className="weekly-board">
              <div className="weekly-title"><span>{t('weeklyBoard')}</span><small>{weeklyBoard.week_id}</small></div>
              <div className="leaderboard-card">{weeklyBoard.entries.length === 0 ? <p className="muted">{t('weeklyEmpty')}</p> : weeklyBoard.entries.map((entry) => <div className="leader-row" key={`w-${entry.rank}-${entry.handle}`}>
                <span>#{String(entry.rank).padStart(2, '0')}</span><strong>{entry.handle}<em>{t(`tier.${entry.tier}`)}</em></strong><small>{entry.correct}/{entry.rounds}</small><b>{entry.score}</b>
              </div>)}</div>
            </div>
          )}
        </section>

        <section className="knowledge-section" id="documentation">
          <div className="knowledge-orbit"><i /><i /><i /><span>∞</span></div>
          <div className="knowledge-copy"><small>AICOM // {t('labelOpenProtocol')}</small><h2>{t('knowledgeTitle')}</h2><p>{t('knowledgeBody')}</p>
            <div className="knowledge-actions">
              <a href={rulesUrl} target="_blank" rel="noreferrer">{t('readRules')} ↗</a>
              <a href={guideUrl} target="_blank" rel="noreferrer">{t('readGuide')} ↗</a>
              <a href={githubRoot} target="_blank" rel="noreferrer">GITHUB ↗</a>
            </div>
          </div>
          <div className="knowledge-facts"><span><b>5</b>{t('factLanguages')}</span><span><b>5</b>{t('factCapabilities')}</span><span><b>0</b>{t('factFixtures')}</span></div>
        </section>
      </>}
    </main>
    <footer><span>AICOM SIGNAL HUNT · AIMARKET PROTOCOL V2 · MIT</span><span>{t('realOnly')}</span></footer>
  </div>;
}
