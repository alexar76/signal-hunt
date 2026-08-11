export type SourceStatus = {
  status: 'ok' | 'unavailable';
  elapsed_ms: number | null;
  http_status?: number;
  error?: string;
};

export type HubSource = {
  id: string;
  name: string;
  capabilities: number;
  share: number | null;
  price_min_usd: number | null;
  price_median_usd: number | null;
  price_max_usd: number | null;
};

export type FollowUp = {
  id: string;
  kind: 'leading_source' | 'price_direction' | 'external_band' | 'slowest_peer' | 'roster_event' | string;
  prompt: string;
  options: string[];
};

export type PrimeState = {
  active: boolean;
  multiplier: number;
  ends_at?: string | null;
  next_starts_at?: string | null;
  locked_for_round?: boolean;
  window_active?: boolean;
  window_multiplier?: number;
};

export type Engagement = {
  presence: {
    active_observers: number;
    solved_this_round: number;
    window_seconds: number;
  };
  cliffhanger: {
    next_opens_at: string;
    teaser: string;
    preview_severity?: string | null;
  };
};

export type Round = {
  id: string;
  created_at: string;
  expires_at: string;
  observation: {
    id: string;
    state_hash: string;
    observed_at: string;
    hub_url: string;
    hub_name: string;
    capabilities: { total: number; local: number; external: number };
    source_count: number;
    sources: HubSource[];
    peer_count?: number;
    peers?: Array<{
      url: string;
      name: string;
      capabilities_count?: number | null;
      latency_ms?: number | null;
      probe_status?: string | null;
    }>;
    latency?: {
      measured_count?: number;
      probed_count?: number;
      unavailable_count?: number;
      max_ms?: number | null;
      median_ms?: number | null;
    };
    sources_status: Record<string, SourceStatus>;
  };
  signal: {
    sealed: boolean;
    severity: 'anomaly' | 'calm';
    history_depth?: number | null;
    code?: string;
    params?: Record<string, unknown>;
  };
  options: string[];
  evidence: { id: string; kind: string }[];
  opened_evidence: string[];
  answer_commitment: string;
  federation_assist: {
    status: 'ok' | 'unavailable';
    capability_id: string;
    source_hub?: string;
    result_hash?: string;
    reason?: string;
    elapsed_ms?: number;
  };
  follow_up?: FollowUp;
  prime?: PrimeState;
  engagement?: Engagement;
  broadcast_available?: boolean;
  submitted: boolean;
  verdict?: Verdict;
};

export type Evidence = {
  round_id: string;
  evidence_id: string;
  opened_count: number;
  kind?: string;
  data: Record<string, unknown>;
};

export type Verdict = {
  round_id: string;
  submitted_at: string;
  selected: string;
  answer: string;
  correct: boolean;
  score: number;
  scoring: {
    brier: number;
    brier_baseline: number;
    skill: number;
    evidence_count: number;
    evidence_factor: number;
    selected_probability: number;
    probability_sum: number;
    base_score?: number;
    follow_up_bonus?: number;
    prime_active?: boolean;
    prime_multiplier?: number;
  };
  follow_up?: {
    answered: boolean;
    correct: boolean;
    bonus: number;
    answer: string;
    selected: string | null;
  };
  prime?: { active: boolean; multiplier: number };
  cliffhanger?: Engagement['cliffhanger'];
  integrity: {
    answer_commitment: string;
    answer_salt: string;
    state_hash: string;
    formula: string;
  };
  progression?: {
    profile: PlayerProfile;
    new_rewards: Reward[];
  };
  broadcast_available?: boolean;
};

export type Reward = {
  code: string;
  kind: 'badge' | 'status';
  rarity: 'common' | 'rare' | 'epic' | 'legendary' | 'status';
  sigil: string;
  accent?: string;
  earned_at: string;
  round_id: string;
};

export type SeasonPassport = {
  week_id: string;
  score: number;
  distinct_diagnoses: string[];
  prime_corrects: number;
  badges: string[];
  targets: { polyglot: number; hunter: number; prime_runner: number };
};

export type DailyStreakMeta = {
  daily_streak: number;
  played_today: boolean;
  shield_available: boolean;
  shield_used: boolean;
  expires_at: string;
  alive: boolean;
};

export type PlayerProfile = {
  id: string;
  handle: string;
  public_profile: boolean;
  created_at: string;
  score: number;
  rounds: number;
  correct: number;
  accuracy: number | null;
  mean_brier: number | null;
  current_streak: number;
  best_streak: number;
  last_played_at: string | null;
  daily_streak?: number;
  daily_streak_meta?: DailyStreakMeta;
  season?: SeasonPassport;
  tier: { code: string; min_score: number; accent: string };
  next_tier: { code: string; min_score: number; accent: string } | null;
  tier_progress: number;
  rewards: Reward[];
};

export type HeroEvent = {
  id: string;
  created_at: string;
  handle: string;
  event_type: 'promotion' | 'achievement' | 'broadcast';
  status: string;
  score: number;
  rounds: number;
  correct: number;
  best_streak: number;
  rewards: string[];
  url: string;
};

export type LeaderboardEntry = {
  rank: number;
  handle: string;
  score: number;
  rounds: number;
  correct: number;
  mean_brier?: number;
  tier: string;
  week_id?: string;
};
