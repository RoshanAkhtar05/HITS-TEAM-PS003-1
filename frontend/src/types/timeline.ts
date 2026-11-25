export interface ReconstructedEvent {
  timestamp: string;
  timestamp_utc?: string | null;
  timestamp_status?: 'timezone_aware' | 'timezone_unknown';
  time_basis?: 'utc' | 'wall_clock_unverified';
  evidence_id?: string | null;
  evidence_sha256?: string | null;
  artifact_id?: string | null;
  record_id?: string | null;
  provenance?: string | Record<string, any> | null;
  provenance_type?: string | null;
  source_record_number?: number | null;
  source_file?: string | null;
  action: string;
  from: string;
  from_id: string;
  to?: string;
  to_id?: string;
  source_type: string;
  confidence: number;
  description: string;
  attributes?: Record<string, any>;
}

export interface TimelineScene {
  scene_id: string;
  window_start: string;
  window_end: string;
  time_basis?: 'utc' | 'wall_clock_unverified';
  timezone_status?: 'verified_offset' | 'timezone_unknown';
  label: string;
  event_count: number;
  action_breakdown: Record<string, number>;
  dominant_source_types: string[];
  active_actors: string[];
  events: ReconstructedEvent[];
}

export interface ReconstructedTimeline {
  generated_at: string;
  incident_window: {
    start: string | null;
    end: string | null;
    duration_minutes: number | null;
    status?: string;
    time_basis?: string;
    event_count?: number;
  };
  incident_windows?: Record<string, {
    start: string;
    end: string;
    duration_minutes: number;
    time_basis: string;
    event_count: number;
  }>;
  stats: {
    total_events: number;
    total_scenes: number;
    action_type_counts: Record<string, number>;
    source_type_counts: Record<string, number>;
    peak_activity_scene: string;
    peak_activity_count: number;
  };
  total_events: number;
  total_scenes: number;
  unplaced_event_count?: number;
  unplaced_events?: Array<Record<string, any>>;
  scenes: TimelineScene[];
}
